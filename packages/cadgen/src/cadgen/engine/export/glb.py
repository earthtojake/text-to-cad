"""GLB: a glTF 2.0 binary of the document.

One mesh per prototype -- its positions and normals one accessor pair, its triangles a
primitive per look (a painted face's colour or material is a primitive of its own), indexed in
16 bits where the mesh has at most 65,535 vertices and in 32 where it has more -- and
a node per placement, named by the placement's path, under one root node named by the
document. A material per look: PBR metallic-roughness, its base colour the part's (or
the paint's), metallic, roughness and emissive from the part's material, ``BLEND`` where
the colour is not opaque, and the rest of the material's look through glTF's material
extensions: ``KHR_materials_ior``, ``_transmission`` with ``_volume`` (its thickness the part's,
the smallest extent of its box; its attenuation the material's transmission colour and depth),
``_clearcoat``, ``_anisotropy`` (along a tangent the mesh carries for it: ``tangents``) and
``_emissive_strength``, each where the look is not glTF's default; a part without a material
is a matte one of its colour. A
placement whose own colour is not its part's is drawn by a second mesh of the same
accessors in that colour. The placements are in the document's millimetres, Z up; the
root node shows them in glTF's frame, Y up and metres, as cadgen's other GLBs do. A mesh of a
format that carries no normals (an STL's, a 3MF's) is given the viewer's (``mesh.shaded``).

Every configuration sequence of the document is an animation of the same name (``export/motion.py``):
translation and rotation channels for each placement it moves, its duration in the animation's
``extras`` (``{"cadgen": {"duration": seconds}}``). A clip is the sequence once; a player repeats
it. After them, the source's animations (``animation()``, ``export/animation.py``), each one glTF
animation of its name: translation, rotation and scale channels on the nodes its references
place, their duration in ``extras`` as a configuration sequence's: a build's, or the record of them an
xbf carries (``animations.record``). Every channel is written LINEAR -- the fewest keys within a
tenth of a millimetre and of a degree of its bake (``export/keys.py``) -- but a STEP one (a hide),
which is written as baked. A placement anything moves stands by translation and
rotation, as glTF asks of an animated node; every other one by its matrix. Channels whose keys
are the same bytes (the parts of one link, or of one reference, that stand where their motion
puts them) point at one sampler, and samplers with the same keys at one accessor: each motion is
written once however many parts it carries, and every part keeps its own node and name.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

import numpy as np

from cadgen.engine.export.mesh import groups, meshes, placed_points, shaded

__all__ = ["write"]

# The glTF 2.0 container (the spec's constants): its magic, version and chunk types.
MAGIC = 0x46546C67
VERSION = 2
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
# The document's Z-up millimetres as glTF's Y-up metres, on the root node: -90 degrees
# about X, then 0.001. The placements below it stay in the document's millimetres.
ROTATION = (-math.sqrt(0.5), 0.0, 0.0, math.sqrt(0.5))
SCALE = (0.001, 0.001, 0.001)


def write(view: Any, path: Path) -> None:
    held = {index: shaded(mesh) for index, mesh in meshes(view).items()}
    blob = bytearray()
    views: list[dict] = []
    accessors: list[dict] = []

    def add(array: np.ndarray, target: int, kind: str, component: int) -> int:
        while len(blob) % 4:
            blob.append(0)
        view_entry = {"buffer": 0, "byteOffset": len(blob), "byteLength": array.nbytes}
        if target is not None:
            view_entry["target"] = target
        views.append(view_entry)
        blob.extend(array.tobytes())
        accessor: dict[str, Any] = {"bufferView": len(views) - 1, "componentType": component,
                                    "count": int(array.shape[0]), "type": kind}
        if kind == "VEC3" and target is not None:
            accessor["min"] = array.min(axis=0).tolist() if len(array) else [0, 0, 0]
            accessor["max"] = array.max(axis=0).tolist() if len(array) else [0, 0, 0]
        accessors.append(accessor)
        return len(accessors) - 1

    materials: list[dict] = []
    material_at: dict[tuple, int] = {}
    used: set[str] = set()

    def material(look: tuple, thickness: float) -> int:
        rgba, held = look
        given = dict(held) if held is not None else None
        # A transmissive look's volume is as thick as the part it is on (``KHR_materials_volume``).
        key = (look, thickness if given is not None and given.get("transmission") else None)
        found = material_at.get(key)
        if found is None:
            entry = _material(rgba, given, thickness)
            used.update(entry.get("extensions", {}))
            materials.append(entry)
            found = material_at[key] = len(materials) - 1
        return found

    gltf_meshes: list[dict] = []
    shared: dict[int, tuple[int, int, dict]] = {}  # prototype -> positions, normals, indices accessor by triangle span
    mesh_at: dict[tuple, int] = {}

    def mesh_of(index: int, color: tuple | None) -> int | None:
        key = (index, color)
        found = mesh_at.get(key)
        if found is not None:
            return found
        mesh = held[index]
        if not mesh.triangles:
            return None
        prototype = view.prototypes[index]
        if index not in shared:
            shared[index] = (add(np.ascontiguousarray(mesh.positions, "<f4"), 34962, "VEC3", 5126),
                             add(np.ascontiguousarray(mesh.normals, "<f4"), 34962, "VEC3", 5126), {})
        positions, normals, spans = shared[index]
        looks = groups(mesh, prototype, color)
        attributes = {"POSITION": positions, "NORMAL": normals}
        if any(look[1] is not None and dict(look[1]).get("anisotropy") for look, _ in looks):
            # An anisotropic look runs along the mesh's tangents, which nothing else gives it.
            if "tangents" not in spans:
                spans["tangents"] = add(np.ascontiguousarray(tangents(mesh.normals), "<f4"), 34962, "VEC4", 5126)
            attributes["TANGENT"] = spans["tangents"]
        thickness = _thickness(mesh)
        # A mesh of at most 65,535 vertices is indexed in 16 bits (core glTF: no extension, and its
        # largest index, 65,534, is short of the primitive restart value), a larger one in 32.
        narrow = accessors[positions]["count"] <= 65535
        primitives = []
        for look, indices in looks:
            span = indices.tobytes()
            accessor = spans.get(span)
            if accessor is None:
                accessor = spans[span] = add(np.ascontiguousarray(indices, "<u2" if narrow else "<u4"), 34963,
                                             "SCALAR", 5123 if narrow else 5125)
            primitives.append({"attributes": dict(attributes), "indices": accessor,
                               "material": material(look, thickness)})
        gltf_meshes.append({"name": prototype["name"], "primitives": primitives})
        found = mesh_at[key] = len(gltf_meshes) - 1
        return found

    nodes: list[dict] = [{"name": view.name, "rotation": list(ROTATION), "scale": list(SCALE), "children": []}]
    node_of: dict[int, int] = {}  # instance index -> node
    shown: list[Any] = []
    for placed in view.placements:
        own = held[placed.prototype]
        color = placed.color if placed.color is not None and placed.color != _tuple(
            view.prototypes[placed.prototype].get("color")) else None
        index = mesh_of(placed.prototype, color) if own.triangles else None
        if index is None:
            continue
        nodes.append({"name": "/".join(placed.path[1:]) or placed.path[-1], "mesh": index,
                      "matrix": [float(value) for value in placed.matrix.T.ravel()]})
        nodes[0]["children"].append(len(nodes) - 1)
        node_of[placed.instance] = len(nodes) - 1
        shown.append(placed)
    animations = _animations(view, held, shown, node_of, nodes, add, accessors)
    document = {"asset": {"version": "2.0", "generator": "cadgen engine"}, "scene": 0,
                "scenes": [{"name": view.name, "nodes": [0]}], "nodes": nodes, "meshes": gltf_meshes,
                "materials": materials, "accessors": accessors, "bufferViews": views,
                "buffers": [{"byteLength": len(blob)}]}
    if animations:
        document["animations"] = animations
    if used:
        document["extensionsUsed"] = sorted(used)
    text = json.dumps(document, separators=(",", ":")).encode()
    text += b" " * (-len(text) % 4)
    while len(blob) % 4:
        blob.append(0)
    with open(path, "wb") as handle:
        handle.write(struct.pack("<III", MAGIC, VERSION, 12 + 8 + len(text) + 8 + len(blob)))
        handle.write(struct.pack("<II", len(text), JSON_CHUNK))
        handle.write(text)
        handle.write(struct.pack("<II", len(blob), BIN_CHUNK))
        handle.write(bytes(blob))


def _material(rgba: tuple, given: dict[str, Any] | None, thickness: float) -> dict[str, Any]:
    """A look as a glTF material: PBR metallic-roughness and an extension for each part of the
    look past it (``materials``' table), each written only where it is not glTF's default."""
    entry: dict[str, Any] = {"pbrMetallicRoughness": {
        "baseColorFactor": list(rgba),
        "metallicFactor": given["metallic"] if given is not None else 0.0,
        "roughnessFactor": given["roughness"] if given is not None else 0.6},
        "doubleSided": False, "alphaMode": "BLEND" if rgba[3] < 1.0 else "OPAQUE"}
    if given is None:
        return entry
    entry["name"] = given["name"]
    extensions: dict[str, Any] = {}
    if any(given.get("emissive") or ()):
        entry["emissiveFactor"] = list(given["emissive"])
        if given.get("emissiveStrength", 1.0) != 1.0:
            extensions["KHR_materials_emissive_strength"] = {"emissiveStrength": given["emissiveStrength"]}
    if given.get("ior", 1.5) != 1.5:
        extensions["KHR_materials_ior"] = {"ior": given["ior"]}
    if given.get("transmission"):
        extensions["KHR_materials_transmission"] = {"transmissionFactor": given["transmission"]}
        volume: dict[str, Any] = {"thicknessFactor": thickness}
        if given.get("transmissionDepth") is not None:
            # Metres: the root node's scale makes the scene's units metres.
            volume["attenuationDistance"] = given["transmissionDepth"]
            volume["attenuationColor"] = list(given.get("transmissionColor") or (1.0, 1.0, 1.0))
        extensions["KHR_materials_volume"] = volume
    if given.get("coat"):
        extensions["KHR_materials_clearcoat"] = {"clearcoatFactor": given["coat"],
                                                 "clearcoatRoughnessFactor": given.get("coatRoughness", 0.0)}
    if given.get("anisotropy"):
        extensions["KHR_materials_anisotropy"] = {"anisotropyStrength": given["anisotropy"],
                                                  "anisotropyRotation": given.get("anisotropyRotation", 0.0)}
    if extensions:
        entry["extensions"] = extensions
    return entry


def _thickness(mesh: Any) -> float:
    """A part's thickness for its volume: the smallest extent of its box, in its millimetres."""
    points = np.asarray(mesh.positions, dtype=np.float32).reshape(-1, 3)
    return float(np.min(points.max(axis=0) - points.min(axis=0))) if len(points) else 0.0


def tangents(normals: Any) -> np.ndarray:
    """A tangent per vertex for an anisotropic look, which has no UVs to take one from: across
    the normal around the part's Z axis (round faces brushed around it), along its Y where the
    normal is Z itself; ``w`` 1. The viewer's scene draws the same."""
    normal = np.asarray(normals, dtype=np.float32).reshape(-1, 3)
    tangent = np.cross(normal, np.array([0.0, 0.0, 1.0], dtype=np.float32))
    flat = np.linalg.norm(tangent, axis=1) < 1e-3
    tangent[flat] = np.cross(normal[flat], np.array([1.0, 0.0, 0.0], dtype=np.float32))
    length = np.linalg.norm(tangent, axis=1, keepdims=True)
    tangent = np.where(length > 0, tangent / np.maximum(length, 1e-12), np.array([1.0, 0.0, 0.0], dtype=np.float32))
    return np.hstack([tangent, np.ones((len(tangent), 1), dtype=np.float32)]).astype(np.float32)


def _size(held: dict[int, Any], shown: list[Any]) -> float:
    """The model's size: the diagonal of every placed mesh's box, in millimetres."""
    low, high = np.full(3, np.inf), np.full(3, -np.inf)
    boxes: dict[int, np.ndarray] = {}
    for placed in shown:
        corners = boxes.get(placed.prototype)
        if corners is None:
            points = np.asarray(held[placed.prototype].positions, dtype=np.float32).reshape(-1, 3)
            least, most = points.min(axis=0), points.max(axis=0)
            corners = boxes[placed.prototype] = np.array(
                [[(least, most)[i][0], (least, most)[j][1], (least, most)[k][2]]
                 for i in (0, 1) for j in (0, 1) for k in (0, 1)], dtype=np.float32)
        moved = placed_points(corners, placed.matrix)
        low, high = np.minimum(low, moved.min(axis=0)), np.maximum(high, moved.max(axis=0))
    return float(np.linalg.norm(high - low)) if np.all(np.isfinite(low)) else 1.0


def _animations(view: Any, held: dict[int, Any], shown: list[Any], node_of: dict[int, int], nodes: list[dict],
                add: Any, accessors: list[dict]) -> list[dict]:
    """Every configuration sequence baked into an animation, then every ``animation()`` of a built source (see the
    module docstring); the nodes they move are given translation and rotation in place of their
    matrices."""
    motions = bool((view.source.structure.get("kinematics") or {}).get("motions"))
    if not node_of or not (motions or getattr(view.source, "animations", None)):
        return []
    from cadgen.engine.export.animation import bake
    from cadgen.engine.export.keys import linear
    from cadgen.engine.export.motion import clips, quaternion

    size = _size(held, shown)
    baked = clips(view, list(node_of), size) if motions else []
    animations = bake(view, held, shown, node_of, size) if getattr(view.source, "animations", None) else []
    animated = sorted({index for clip in baked for index in clip.instances}
                      | {channel.instance for animation in animations for channel in animation.channels})
    rest = {placed.instance: placed.matrix for placed in shown}
    for index in animated:
        node = nodes[node_of[index]]
        matrix = np.asarray(rest[index], dtype=float)
        node.pop("matrix")
        node["translation"] = [float(value) for value in matrix[:3, 3]]
        node["rotation"] = [float(value) for value in quaternion(matrix)]
    # A part's motion is every part's that moves with it: the parts of one link, or of one reference, each
    # its own node, stand where their motion puts them, so their channels' keys are the same bytes. Those
    # channels share one sampler, and every sampler with the same keys one key accessor, so each motion is
    # written once however many parts it carries.
    data: dict[tuple, int] = {}

    def accessor(rows: np.ndarray, kind: str) -> int:
        array = np.ascontiguousarray(rows, "<f4")
        key = (kind, array.tobytes())
        found = data.get(key)
        if found is None:
            found = data[key] = add(array, None, kind, 5126)
            if kind == "SCALAR":
                accessors[found]["min"] = [float(array[0])]
                accessors[found]["max"] = [float(array[-1])]
        return found

    # Every track but a STEP one is written as the fewest LINEAR keys within KEY_MM and KEY_DEGREES of
    # its bake (``export/keys.py``), each distinct track worked out once; a scale is held to the
    # millimetres its part moves, by the part's reach.
    placed_at = {placed.instance: placed for placed in shown}
    reaches: dict[int, float] = {}
    written: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}

    def reach(index: int) -> float:
        prototype = placed_at[index].prototype
        if prototype not in reaches:
            points = np.asarray(held[prototype].positions, dtype=float).reshape(-1, 3)
            reaches[prototype] = float(np.max(np.linalg.norm(points, axis=1))) if len(points) else 0.0
        return reaches[prototype]

    def keyed(index: int, path: str, interpolation: str, times: np.ndarray, rows: np.ndarray,
              duration: float) -> tuple[str, np.ndarray, np.ndarray]:
        if interpolation == "STEP":
            return interpolation, times, rows
        far = reach(index) if path == "scale" else 0.0
        key = (path, interpolation, duration, far, np.asarray(times, dtype=float).tobytes(),
               np.asarray(rows, dtype=float).tobytes())
        if key not in written:
            written[key] = linear(times, rows, interpolation, path, duration, far)
        return "LINEAR", *written[key]

    found = []

    def animation(name: str, duration: float, tracks: list[tuple[int, str, str, np.ndarray, np.ndarray]]) -> None:
        samplers: list[dict] = []
        channels: list[dict] = []
        shared: dict[tuple, int] = {}
        for index, path, interpolation, times, rows in tracks:
            interpolation, times, rows = keyed(index, path, interpolation, times, rows, duration)
            kind = "VEC4" if path == "rotation" else "VEC3"
            entry = {"input": accessor(times, "SCALAR"), "interpolation": interpolation,
                     "output": accessor(rows.reshape(-1, rows.shape[-1]), kind)}
            key = (entry["input"], interpolation, entry["output"])
            if key not in shared:
                shared[key] = len(samplers)
                samplers.append(entry)
            channels.append({"sampler": shared[key], "target": {"node": node_of[index], "path": path}})
        found.append({"name": name, "channels": channels, "samplers": samplers,
                      "extras": {"cadgen": {"duration": duration}}})

    for clip in baked:
        if clip.instances:
            animation(clip.name, clip.duration, [
                (index, path, "CUBICSPLINE", clip.times, rows)
                for index, translations, rotations in zip(clip.instances, clip.translations, clip.rotations)
                for path, rows in (("translation", translations), ("rotation", rotations))])
    for baked_animation in animations:
        if baked_animation.channels:
            animation(baked_animation.name, baked_animation.duration, [
                (channel.instance, channel.path, channel.interpolation, channel.times, channel.values)
                for channel in baked_animation.channels])
    return found


def _tuple(value: Any) -> tuple | None:
    return tuple(value) if value is not None else None
