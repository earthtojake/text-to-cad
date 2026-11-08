"""An SDF (SDFormat) read into a robot's articulation (``robot_model``): what the stills
(``formats/robot.py``) and the viewer's payload (the server's ``robot_payload``) each take a view of.
In the engine, as ``mjcf_source`` is, because every reader of an SDF reads it here; the standard
library alone (``tests/python/global/test_robot_modules_stdlib_pure.py``). The type's own check is the
validation family's (``cad.sdf._validation``), which the payload runs first.

**What is read**: one model -- the document's one direct ``<model>``, or its one ``<world>``'s one
direct ``<model>`` -- and every model nested in it (SDFormat 1.6+), as one frame graph by the
SDFormat rules: links, frames, joints and nested models keyed by scoped name (``arm::elbow``), a name
written in a nested model resolved in that model's namespace; a pose ``relative_to`` a frame (by
default, a link's and a frame's the model's, a joint's its child's, a visual's its link's), a frame
``attached_to`` another, a nested model posed in the model it is nested in and attached to its
``canonical_link`` (else its first link); a joint's axis ``expressed_in`` a frame (by default its
own); ``euler_rpy`` poses, in degrees where ``degrees`` says so. Each link's visuals: a mesh's
``<uri>`` resolved to its file (``mesh_uri``, as a URDF's is: ``urdf_source.mesh_file``) with its
``<scale>``, or a box, cylinder, sphere or capsule in full sizes, the material's diffuse (else
ambient) colour. A joint names its links by what its parent and child frames are attached to; one on
the world has no parent link. Every link is placed at rest in the model's world; the root is the one
link no joint carries, "" when the links float free of one root. With the dialect's ``facts``, what
the description writes -- each visual's and collision's geometry and pose, each joint's pose, axis
and limit, and the document's account of itself (``sdf``: its version, its world, its counts, its
includes, plugins, sensors, lights and physics) -- is read as written.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

from cad.engine.robot_model import (IDENTITY, MOVING, Articulation, Dialect, LinkJoint, Visual, children,
                                    described_origin, first, hex_color, invert_rigid, local_name, multiply, numbers,
                                    optional_numbers, parse, pose, rotate, text, unit)
from cad.engine.urdf_source import mesh_file

__all__ = ["read_sdf"]

_MODEL_FRAME = "__model__"
_WORLD_FRAME = "world"
#: The shapes a visual is drawn as, besides a mesh: what ``unsupportedCollisionCount`` counts the rest against.
SHAPES = ("box", "capsule", "cylinder", "sphere")


class _Scope:
    """One model's namespace in the frame graph: the top-level model's (no prefix, its frame
    ``__model__``) or a nested model's (``arm::``, its frame the node ``arm``), and the names
    its links, frames, joints and nested models declare."""

    __slots__ = ("name", "prefix", "frame", "declared")

    def __init__(self, model: ET.Element, prefix: str, frame: str) -> None:
        self.name, self.prefix, self.frame = str(model.get("name") or "").strip(), prefix, frame
        self.declared = {str(element.get("name") or "").strip()
                         for tag in ("link", "frame", "joint", "model") for element in children(model, tag)}

    def own(self, element: ET.Element) -> str:
        """The graph key of an element this model declares."""
        return self.prefix + str(element.get("name") or "").strip()

    def key(self, name: object, default: str) -> str:
        """The graph key a name written in this model means: what the model declares by that
        name, ``world`` for the world, the model's own frame for ``__model__`` or its own name,
        else the name in this model's namespace -- a scoped name (``hand::palm``) reaching
        into a model nested in it."""
        written = str(name or "").strip()
        if not written:
            return default
        if written in self.declared:
            return self.prefix + written
        if written == _WORLD_FRAME:
            return _WORLD_FRAME
        if written in (self.name, _MODEL_FRAME):
            return self.frame
        return self.prefix + written


class _Frames:
    """The model's frame graph: its links, frames, joints and nested models, and theirs, keyed by
    scoped name, to their rest transforms in the model's world. Every node's ``relative_to`` is a
    key, resolved in its own model's namespace when it was added."""

    def __init__(self, model: str, world: list[list[float]], dialect: Dialect) -> None:
        self.model, self.dialect = model, dialect
        self.nodes: dict[str, dict[str, Any]] = {
            _WORLD_FRAME: {"kind": "world", "world": IDENTITY},
            _MODEL_FRAME: {"kind": "model", "world": world, "canonical": ""},
        }
        self.links: set[str] = set()

    def add(self, key: str, node: dict[str, Any]) -> None:
        if key in self.nodes:
            raise self.dialect.error("frame_twice", model=self.model, key=key)
        self.nodes[key] = node

    def world(self, key: str, resolving: tuple[str, ...] = ()) -> list[list[float]]:
        node = self.nodes.get(key)
        if node is None:
            raise self.dialect.error("frame_unknown", model=self.model, key=key)
        if "world" in node:
            return node["world"]
        if key in resolving:
            raise self.dialect.error("frame_cycle", model=self.model, key=key)
        node["world"] = multiply(self.world(node["relative_to"], (*resolving, key)), node["pose"])
        return node["world"]

    def attached_link(self, key: str, resolving: tuple[str, ...] = ()) -> str:
        """The link a frame moves with ("" for the world): a frame's what it is attached to, a joint's
        its child's, a nested model's its canonical link's."""
        if key in self.links:
            return key
        if key == _WORLD_FRAME:
            return ""
        node = self.nodes.get(key)
        if node is None:
            if self.dialect.refuses("attached_unknown"):
                raise self.dialect.error("attached_unknown", model=self.model, key=key)
            return ""
        if key in resolving:
            if self.dialect.refuses("attached_cycle"):
                raise self.dialect.error("attached_cycle", model=self.model, key=key)
            return ""
        follow = {"frame": node.get("attached"), "joint": node.get("child"), "model": node.get("canonical")}.get(node["kind"])
        return self.attached_link(follow, (*resolving, key)) if follow else ""


def _pose(element: ET.Element, where: str, dialect: Dialect) -> tuple[str, list[float], list[list[float]]]:
    """``(relative_to, values, transform)`` of an element's ``<pose>``."""
    found = first(element, "pose")
    if found is None:
        return "", [0.0] * 6, IDENTITY
    rotation_format = str(found.get("rotation_format") or "euler_rpy").strip().lower()
    if rotation_format != "euler_rpy":
        raise dialect.error("rotation_format", where=where, format=rotation_format)
    values = numbers(found.text, 6, f"{where} pose", dialect, default=[0.0] * 6) or [0.0] * 6
    if str(found.get("degrees") or "").strip().lower() in dialect.degrees:
        values[3:] = [math.radians(value) for value in values[3:]]
    return str(found.get("relative_to") or "").strip(), values, pose(values[:3], values[3:])


def _shape_facts(owner: ET.Element, where: str, dialect: Dialect) -> dict[str, Any]:
    """A visual's or a collision's name, geometry and pose as written."""
    geometry = first(owner, "geometry")
    _relative, values, _transform = _pose(owner, where, dialect)
    facts: dict[str, Any] = {"name": str(owner.get("name") or "").strip(), "type": "unknown", "filename": "",
                             "origin": described_origin(values[:3], values[3:])}
    shapes = [child for child in list(geometry) if isinstance(child.tag, str)] if geometry is not None else []
    if not shapes:
        facts["type"] = "missing"
        return facts
    shape = shapes[0]
    kind = local_name(shape.tag)
    facts["type"] = kind
    if kind == "mesh":
        facts["filename"] = text(shape, "uri")
        facts["scale"] = optional_numbers(text(shape, "scale"), 3)
    elif kind == "box":
        facts["size"] = optional_numbers(text(shape, "size"), 3)
    elif kind in ("cylinder", "sphere", "capsule"):
        radius = optional_numbers(text(shape, "radius"), 1)
        facts["radius"] = radius[0] if radius else None
        if kind != "sphere":
            length = optional_numbers(text(shape, "length"), 1)
            facts["length"] = length[0] if length else None
    return facts


def _drawable(facts: dict[str, Any]) -> bool:
    """Whether a shape as ``_shape_facts`` describes it is one a visual may be: a mesh by its uri, or
    one of ``SHAPES`` with its dimensions."""
    kind = facts.get("type")
    if kind == "mesh":
        return bool(facts.get("filename"))
    if kind == "box":
        return facts.get("size") is not None
    return kind in SHAPES and facts.get("radius") is not None and (kind == "sphere" or facts.get("length") is not None)


def _shape(owner: ET.Element, base: Path, where: str, dialect: Dialect) -> tuple[tuple, str]:
    """A visual's shape (``robot_model``'s) and its mesh reference as written ("" for a primitive);
    ``(kind,)`` for geometry no visual is drawn as (``missing`` where it has none)."""
    geometry = first(owner, "geometry")
    shape = next((child for child in (geometry if geometry is not None else []) if isinstance(child.tag, str)), None)
    kind = local_name(shape.tag) if shape is not None else "missing"
    if kind == "mesh":
        uri = text(shape, "uri")
        scale = numbers(text(shape, "scale"), 3, where, dialect, default=[1.0, 1.0, 1.0], code="sdf_scale")
        return ("file", mesh_file(uri, base, where) if uri else None, scale), uri
    if kind == "box":
        return ("box", {"size": numbers(text(shape, "size"), 3, f"{where} box size", dialect)}), ""
    if kind in ("cylinder", "capsule", "sphere"):
        dimensions: dict[str, float] = {}
        for key in ("radius", "length") if kind != "sphere" else ("radius",):
            found = optional_numbers(text(shape, key), 1)
            if found is not None:
                dimensions[key] = found[0]
        return (kind, dimensions), ""
    return (kind,), ""


def _color(owner: ET.Element) -> tuple[float, ...] | None:
    """A visual's material colour: its diffuse, else its ambient (three or four numbers)."""
    material = first(owner, "material")
    if material is None:
        return None
    for tag in ("diffuse", "ambient"):
        raw = text(material, tag).split()
        if len(raw) in (3, 4):
            values = optional_numbers(" ".join(raw), len(raw))
            if values is not None:
                return tuple(values)
    return None


def _model(root: ET.Element, file: str, dialect: Dialect) -> tuple[str, str, ET.Element]:
    """``(document kind, world name, the model element)``: the one model a document holds."""
    models = children(root, "model")
    if len(models) == 1:
        return "model", "", models[0]
    if len(models) > 1:
        raise dialect.error("sdf_models", file=file, count=len(models))
    worlds = children(root, "world")
    if len(worlds) != 1:
        raise dialect.error("sdf_worlds", file=file)
    world_models = children(worlds[0], "model")
    if len(world_models) != 1:
        raise dialect.error("sdf_world_models", file=file, count=len(world_models))
    return "world", str(worlds[0].get("name") or "").strip(), world_models[0]


def _metadata(root: ET.Element) -> dict[str, Any]:
    """What a document says about itself beyond its links and joints: its includes, plugins, sensors,
    lights and physics, and how many models are nested in models."""
    def attributes(element: ET.Element, names: tuple[str, ...]) -> dict[str, str]:
        return {name: str(element.get(name) or "").strip() for name in names if str(element.get(name) or "").strip()}

    def descendants(tag: str) -> list[ET.Element]:
        return [element for element in root.iter() if isinstance(element.tag, str) and local_name(element.tag) == tag]

    nested = 0
    parents = {child: parent for parent in root.iter() for child in parent}
    for model in descendants("model"):
        parent = parents.get(model)
        if parent is not None and local_name(parent.tag) == "model":
            nested += 1
    return {
        "includes": [{"id": f"include:{index}", "uri": text(element, "uri"), "name": text(element, "name")}
                     for index, element in enumerate(descendants("include"), start=1)],
        "plugins": [{"id": f"plugin:{index}", **attributes(element, ("name", "filename"))}
                    for index, element in enumerate(descendants("plugin"), start=1)],
        "sensors": [{"id": f"sensor:{index}", **attributes(element, ("name", "type"))}
                    for index, element in enumerate(descendants("sensor"), start=1)],
        "lights": [{"id": f"light:{index}", **attributes(element, ("name", "type"))}
                   for index, element in enumerate(descendants("light"), start=1)],
        "physics": [{"id": f"physics:{index}", **attributes(element, ("name", "type", "default"))}
                    for index, element in enumerate(descendants("physics"), start=1)],
        "nestedModelCount": nested,
    }


def read_sdf(path: Path, dialect: Dialect | None = None) -> Articulation:
    """``path`` read as an SDF into its model's articulation at rest, or refused by name (``SourceError``)."""
    dialect = dialect or Dialect()
    path = Path(path)
    file, base = dialect.display(path), path.parent
    root = parse(path, dialect)
    if local_name(root.tag) != "sdf":
        raise dialect.error("sdf_root", file=file)
    document_kind, world_name, model = _model(root, file, dialect)
    model_name = str(model.get("name") or "").strip()
    relative_to, _values, model_world = _pose(model, f"{file} model {model_name!r}", dialect)
    if relative_to and relative_to != _WORLD_FRAME and dialect.refuses("model_relative"):
        raise dialect.error("model_relative", file=file, model=model_name, relative=relative_to)
    frames = _Frames(model_name, model_world, dialect)
    link_elements: list[tuple[str, ET.Element, _Scope]] = []
    frame_count = 0
    raw_joints: list[dict[str, Any]] = []

    def collect(element: ET.Element, scope: _Scope) -> None:
        nonlocal frame_count
        if str(element.get("placement_frame") or "").strip() and dialect.refuses("placement_frame"):
            raise dialect.error("placement_frame", file=file, where=f"{file} model {(scope.prefix[:-2] or model_name)!r}")
        for link in children(element, "link"):
            key = scope.own(link)
            relative, _values, transform = _pose(link, f"{file} link {key!r}", dialect)
            frames.links.add(key)
            frames.add(key, {"kind": "link", "pose": transform, "relative_to": scope.key(relative, scope.frame)})
            link_elements.append((key, link, scope))
        for frame in children(element, "frame"):
            key = scope.own(frame)
            attached = scope.key(frame.get("attached_to"), scope.frame)
            relative, _values, transform = _pose(frame, f"{file} frame {key!r}", dialect)
            frames.add(key, {"kind": "frame", "pose": transform, "relative_to": scope.key(relative, attached),
                             "attached": attached})
            frame_count += 1
        for nested in children(element, "model"):
            key = scope.own(nested)
            relative, _values, transform = _pose(nested, f"{file} model {key!r}", dialect)
            inner = _Scope(nested, f"{key}::", key)
            canonical = str(nested.get("canonical_link") or "").strip()
            first_link = first(nested, "link") if not canonical else None
            first_model = (first(nested, "model") if dialect.canonical_model and not canonical and first_link is None
                           else None)
            canonical_key = (inner.key(canonical, "") if canonical else inner.own(first_link) if first_link is not None
                             else inner.own(first_model) if first_model is not None else "")
            frames.add(key, {"kind": "model", "pose": transform, "relative_to": scope.key(relative, scope.frame),
                             "canonical": canonical_key})
            collect(nested, inner)
        for joint in children(element, "joint"):
            key = scope.own(joint)
            kind = str(joint.get("type") or "").strip().lower()
            if kind not in (*MOVING, "fixed"):
                raise dialect.error("sdf_joint_type", file=file, joint=key, kind=kind)
            parent = scope.key(text(joint, "parent"), "")
            child = scope.key(text(joint, "child"), "")
            relative, values, transform = _pose(joint, f"{file} joint {key!r}", dialect)
            frames.add(key, {"kind": "joint", "pose": transform, "relative_to": scope.key(relative, child), "child": child})
            axis_element = first(joint, "axis")
            xyz = first(axis_element, "xyz")
            axis = numbers(xyz.text if xyz is not None else None, 3, f"{file} joint {key!r} axis", dialect,
                           default=[0.0, 0.0, 1.0]) or [0.0, 0.0, 0.0]
            expressed_in = ((xyz.get("expressed_in") if xyz is not None else None)
                            or (axis_element.get("expressed_in") if axis_element is not None else None))
            limit_element = first(axis_element, "limit")
            limit: dict[str, float] = {}
            for name in ("lower", "upper", "effort", "velocity"):
                value = optional_numbers(text(limit_element, name), 1) if limit_element is not None else None
                if value is not None:
                    limit[name] = value[0]
            raw_joints.append({"name": key, "type": kind, "parent": parent, "child": child, "axis": axis,
                               "expressed_in": scope.key(expressed_in, key), "limit": limit,
                               "declared_limit": limit_element is not None, "pose": values})

    collect(model, _Scope(model, "", _MODEL_FRAME))

    links: dict[str, list[list[float]]] = {}
    visuals: dict[str, list[Visual]] = {}
    collisions: dict[str, list[dict[str, Any]]] = {}
    for key, element, scope in link_elements:
        links[key] = frames.world(key)
        inverse = invert_rigid(links[key])
        visuals[key] = []
        for index, visual in enumerate(children(element, "visual"), start=1):
            where = f"{file} link {key!r} visual {index}"
            facts = _shape_facts(visual, where, dialect) if dialect.facts else None
            rgba = _color(visual)
            color = hex_color(rgba) if rgba is not None else ""
            relative, _values, transform = _pose(visual, where, dialect)
            local = multiply(inverse, multiply(frames.world(scope.key(relative, key)), transform))
            shape, reference = _shape(visual, base, where, dialect)
            if facts is not None:
                facts["color"], facts["materialName"] = color, ""
                if shape[0] == "file" and shape[1] is not None:
                    facts["path"] = str(shape[1])
            name = str(visual.get("name") or "").strip()
            label = name or (shape[1].name if shape[0] == "file" and shape[1] is not None else shape[0] if shape[0] != "file"
                             else Path(reference).name or "mesh")
            visuals[key].append(Visual(f"{key}:v{index}", key, local, shape, color, 1.0 if rgba is None or len(rgba) < 4
                                       else rgba[3], label, reference=reference, rgba=rgba, facts=facts))
        if dialect.facts:
            collisions[key] = [_shape_facts(collision, f"{file} link {key!r} collision {index}", dialect)
                               for index, collision in enumerate(children(element, "collision"), start=1)]

    joints: list[LinkJoint] = []
    children_of: set[str] = set()
    for raw in raw_joints:
        parent = frames.attached_link(raw["parent"]) if raw["parent"] else ""
        child = frames.attached_link(raw["child"]) if raw["child"] else ""
        if not child:
            raise dialect.error("joint_unattached", file=file, joint=raw["name"], child=raw["child"])
        if parent == child:
            raise dialect.error("joint_same", file=file, joint=raw["name"], link=child)
        if child in children_of and dialect.refuses("multiple_parents"):
            raise dialect.error("multiple_parents", file=file, link=child)
        children_of.add(child)
        joint = LinkJoint(raw["name"], raw["type"], parent, child, frames.world(raw["name"]), None, None, None)
        if joint.type != "fixed":
            joint.axis = unit(rotate(frames.world(raw["expressed_in"]), raw["axis"]))
            if joint.axis is None:
                raise dialect.error("axis_zero", file=file, joint=raw["name"])
            if joint.type != "continuous":
                joint.lower, joint.upper = raw["limit"].get("lower"), raw["limit"].get("upper")
        if dialect.facts:
            joint.facts = {
                "name": joint.name, "type": joint.type, "parent": parent, "child": child,
                "axis": None if joint.type == "fixed" else list(raw["axis"]),
                "origin": described_origin(raw["pose"][:3], raw["pose"][3:]),
                "limit": raw["limit"] if raw["declared_limit"] else None,
                "mimic": None,
                "fourBar": None,
            }
        joints.append(joint)
    roots = [key for key in links if key not in children_of]
    root_link = roots[0] if len(roots) == 1 else ""
    account = None
    if dialect.facts:
        account = {
            "version": str(root.get("version") or "").strip(),
            "documentKind": document_kind,
            "worldName": world_name,
            "modelName": model_name,
            "rootLink": root_link,
            "rootLinks": roots,
            "frameCount": frame_count,
            "linkCount": len(link_elements),
            "jointCount": len(raw_joints),
            # The collisions with geometry no visual is drawn as (a <plane>, a <heightmap>, none at all):
            # never refused, since no collision is drawn, but counted.
            "unsupportedCollisionCount": sum(not _drawable(facts) for found in collisions.values() for facts in found),
            "staticMetadata": _metadata(root),
        }
    return Articulation(root_link, links, visuals, joints, {}, {}, name=model_name, collisions=collisions, sdf=account,
                        sources=[path])
