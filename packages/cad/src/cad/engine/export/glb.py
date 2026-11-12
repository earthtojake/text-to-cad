"""GLB: a glTF 2.0 binary of the document.

One mesh per prototype -- its positions and normals one accessor pair, its triangles a
primitive per look (a painted face's colour or material is a primitive of its own), indexed in
16 bits where the mesh has at most 65,535 vertices and in 32 where it has more -- and the
document's assembly tree as nodes, under one root node named by the document: a node per
sub-assembly, its components under it, and a node per placement, each placed in its parent's frame
(a node at its parent's place has no matrix), so a part stands where the document places it.
Every node is named by its path below the root (``board/D44/housing``, its sub-assemblies
``board`` and ``board/D44``), unique where the document's own paths are (two sub-assemblies both
labelled ``leg``, each holding a ``foot``, give ``leg``, ``leg/foot``, ``leg``, ``leg/foot``), and a
part's name is the one a flat file gave it. A
sub-assembly with no part the file draws has no node. A material per look: PBR metallic-roughness, its base colour the part's (or
the paint's), metallic, roughness and emissive from the part's material, ``BLEND`` where
the colour is not opaque (a transmissive look's fade is its PBR ``opacity`` alone: ``_alpha``), and
the rest of the material's look through glTF's material
extensions: ``KHR_materials_ior``, ``_transmission`` with ``_volume`` (its thickness the part's,
the smallest extent of its box; its attenuation the material's transmission colour and depth),
``_clearcoat``, ``_anisotropy`` (along a tangent the mesh carries for it: ``tangents``) and
``_emissive_strength``, each where the look is not glTF's default; a part without a material
is a matte one of its colour. A
placement whose own colour is not its part's is drawn by a second mesh of the same
accessors in that colour. The nodes are in the document's millimetres, Z up; the
root node shows them in glTF's frame, Y up and metres. A mesh of a
format that carries no normals (an STL's, a 3MF's) is given the viewer's (``mesh.shaded``). An
export's own tolerance and angle are said in ``asset.extras.cad`` (``meshedWithin`` in millimetres,
``angle`` in degrees), each only where the export gave it.

Every configuration sequence of the document is an animation of the same name (``export/motion.py``):
translation and rotation channels for each placement it moves, its duration and its kind in the
animation's ``extras`` (``{"cad": {"duration": seconds, "kind": "motion"}}``). A clip is the sequence
once; a player repeats it. After them, the source's animations (``animation()``, ``export/animation.py``),
each one glTF animation of its name: translation, rotation and scale channels on the nodes its
references place, ``extras`` as a configuration sequence's (``"kind": "animation"``): a build's, or the
record of them an xbf carries (``animations.record``). A clip keys a sub-assembly that moves as one
(every part under it one link's, or moved by the same references, none scaled) on its own node, and
every other moving part on its own (``motion.chosen``); its keys are in its parent's frame, worked out
from the bake's place in the document's frame (``_local_rows``), the parent standing still in that
clip, so every part is where the bake puts it. Every channel is written LINEAR -- the fewest keys within a
tenth of a millimetre and of a degree of its bake (``export/keys.py``) -- but a STEP one (a hide),
which is written as baked. A node anything moves stands by translation and
rotation, as glTF asks of an animated node; every other one by its matrix. Channels whose keys
are the same bytes (the parts of one link, or of one reference, that stand where their motion
puts them) point at one sampler, and samplers with the same keys at one accessor: each motion is
written once however many nodes it carries.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

import numpy as np

from cad.engine.export.mesh import groups, meshes, placed_points, shaded
from cad.engine.export.motion import Target, quaternion

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
        given = json.loads(held) if held is not None else None
        # A transmissive look's volume is as thick as the part it is on (``KHR_materials_volume``).
        key = (look, thickness if given is not None and given["pbr"]["values"].get("transmission") else None)
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
        if any(look[1] is not None and json.loads(look[1])["pbr"]["values"].get("anisotropy") for look, _ in looks):
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

    drawn: dict[int, int] = {}  # instance index -> its mesh, for each placement the file draws
    for placed in view.placements:
        own = held[placed.prototype]
        color = placed.color if placed.color is not None and placed.color != _tuple(
            view.prototypes[placed.prototype].get("color")) else None
        index = mesh_of(placed.prototype, color) if own.triangles else None
        if index is not None:
            drawn[placed.instance] = index
    nodes, targets = _tree(view, drawn)
    shown = [placed for placed in view.placements if placed.instance in drawn]
    animations = _animations(view, held, shown, targets, nodes, add, accessors)
    asked = {**({} if view.tolerance is None else {"meshedWithin": view.tolerance}),
             **({} if view.angle is None else {"angle": view.angle})}
    document = {"asset": {"version": "2.0", "generator": "cad", **({"extras": {"cad": asked}} if asked else {})},
                "scene": 0,
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
    look past it (``materials``' table), each written only where it is not glTF's default. Its
    scalar look alone: a texture map needs UVs the mesh has none of, so the file has no image and the
    export names what it left out (``untextured``, ``export.translate``)."""
    if given is None:
        return {"pbrMetallicRoughness": {"baseColorFactor": list(rgba), "metallicFactor": 0.0,
                                         "roughnessFactor": 0.6},
                "doubleSided": False, "alphaMode": "BLEND" if rgba[3] < 1.0 else "OPAQUE"}
    from cad.engine.document import pbr_from_json, scalar_pbr

    pbr = pbr_from_json(scalar_pbr(given["pbr"]))
    pbr = pbr.override(metalness=0.0 if pbr.values.metalness is None else pbr.values.metalness,
                       roughness=0.5 if pbr.values.roughness is None else pbr.values.roughness)
    entry = json.loads(pbr.to_gltf().to_json())["materials"][0]
    # Named by its look (``frame_black``), which is what tells two looks of one physical material apart and
    # what a render script restyles by; the physical material's own name (``Alu_G7075_T6``) rides beside it.
    entry["name"] = str(given["pbr"].get("name") or given["material"]["name"])
    entry.setdefault("extras", {})["cad"] = {"material": given["material"]["name"]}
    alpha = _alpha(rgba, pbr.values)
    entry["pbrMetallicRoughness"]["baseColorFactor"] = [*rgba[:3], alpha]
    entry["alphaMode"] = "BLEND" if alpha < 1.0 else "OPAQUE"
    if pbr.values.transmission:
        volume = entry.setdefault("extensions", {}).setdefault("KHR_materials_volume", {})
        volume["thicknessFactor"] = thickness
    return entry


def _alpha(rgba: tuple, values: Any) -> float:
    """A look's alpha: its colour's, but for a transmissive look, which is see-through by its transmission
    and fades only by its PBR ``opacity``. Its colour's alpha there says nothing the file should repeat:
    build123d's material setter infers a preview from the transmission when the material is assigned
    (``PbrProperties.interpolate_color``: ``transmission=1`` gives 0.3), a renderer applying both would draw
    the part refractive and most of it absent, and nothing tells that value from a colour set by hand. What
draws no transmission draws this alpha's preview (``formats/gltf.py``'s ``preview_alpha``, ``drawn_alpha``):
``packages/core``'s ``previewOpacity.parity.json`` holds the two, and the viewer's and the 3MF's, to one set of cases."""
    if not values.transmission:
        return float(rgba[3])
    return 1.0 if values.opacity is None else min(float(values.opacity), 1.0)


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


def _tree(view: Any, drawn: dict[int, int]) -> tuple[list[dict], list[Target]]:
    """The document's tree as glTF nodes, the root first and every node before those under it, and
    each node but the root as a ``motion.Target``: what a clip may key. ``drawn`` is each placement the
    file draws, by instance, its mesh. A sub-assembly stands at its placement in its parent's
    (``Source.locals``, the identity where the document has none: a mesh file's), a part where the
    document places it; a node at its parent's place has no matrix. Each node is named by its path
    below the root, as unique as the document's paths: two siblings of one label share a name."""
    locals_ = view.source.locals()
    placed_at = {placed.instance: placed for placed in view.placements}
    nodes: list[dict] = [{"name": view.name, "rotation": list(ROTATION), "scale": list(SCALE), "children": []}]
    targets: list[Target] = []

    def members(tree: dict[str, Any]) -> tuple[int, ...]:
        if "children" not in tree:
            return (tree["instance"],) if tree["instance"] in drawn else ()
        return tuple(index for child in tree["children"] for index in members(child))

    def visit(tree: dict[str, Any], path: tuple[int, ...], names: list[str], parent: int, within: np.ndarray) -> None:
        under = members(tree)
        if not under:
            return
        given = locals_.get(path)
        local = np.eye(4) if given is None else np.array(given, dtype=float).reshape(4, 4).T
        if "children" in tree:
            name = "/".join(names[1:])
            world = within @ local
        else:
            placed = placed_at[tree["instance"]]
            name = "/".join(placed.path[1:]) or placed.path[-1]
            world = np.asarray(placed.matrix, dtype=float)
            # A part stands where the document places it: at its own placement in its assembly where that
            # puts it there, else (a posed structure) where its instance stands, in its assembly's frame.
            if given is None or not np.allclose(within @ local, world, rtol=0.0, atol=1e-9):
                local = world if np.array_equal(within, np.eye(4)) else np.linalg.inv(within) @ world
        node: dict[str, Any] = {"name": name}
        if "children" not in tree:
            node["mesh"] = drawn[tree["instance"]]
        if not np.array_equal(local, np.eye(4)):
            node["matrix"] = [float(value) for value in local.T.ravel()]
        nodes.append(node)
        index = len(nodes) - 1
        nodes[parent].setdefault("children", []).append(index)
        targets.append(Target(index, None if parent == 0 else parent, under,
                              None if "children" in tree else tree["instance"], world, within, name))
        for at, child in enumerate(tree.get("children") or ()):
            visit(child, path + (at,), names + [child["name"]], index, world)

    tree = view.tree
    if "children" in tree:
        for at, child in enumerate(tree["children"]):
            visit(child, (at,), [tree["name"], child["name"]], 0, np.eye(4))
    else:
        visit(tree, (), [tree["name"]], 0, np.eye(4))
    return nodes, targets


def _conjugate_left(q: np.ndarray) -> np.ndarray:
    """The 4x4 that multiplies a quaternion (x, y, z, w) on the left by ``q``'s conjugate."""
    x, y, z, w = -q[0], -q[1], -q[2], q[3]
    return np.array([[w, -z, y, x], [z, w, -x, y], [-y, x, w, z], [-x, -y, -z, w]])


def _local_rows(path: str, interpolation: str, rows: np.ndarray, within: np.ndarray) -> np.ndarray:
    """A track's rows, the bake's place in the document's frame, made its node's parent's (``within``,
    which stands still while the clip plays): a translation ``R^T (v - t)`` (a CUBICSPLINE tangent
    ``R^T v``), a rotation the parent's conjugate times it (values and tangents alike: the product is
    linear, so the curve between two keys is the parent's of the bake's curve), a scale as it is."""
    if path == "scale" or np.array_equal(within, np.eye(4)):
        return rows
    rows = np.asarray(rows, dtype=float)
    if path == "translation":
        turned = rows @ within[:3, :3]
        offset = within[:3, 3] @ within[:3, :3]
        if interpolation == "CUBICSPLINE":
            turned = turned.copy()
            turned[:, 1] -= offset
            return turned
        return turned - offset
    return rows @ _conjugate_left(quaternion(within)).T


def _animations(view: Any, held: dict[int, Any], shown: list[Any], targets: list[Target], nodes: list[dict],
                add: Any, accessors: list[dict]) -> list[dict]:
    """Every configuration sequence baked into an animation, then every ``animation()`` of a built source (see the
    module docstring); the nodes they move are given translation and rotation in place of their
    matrices."""
    motions = bool((view.source.structure.get("kinematics") or {}).get("motions"))
    if not targets or not (motions or getattr(view.source, "animations", None)):
        return []
    from cad.engine.export.animation import bake
    from cad.engine.export.keys import linear
    from cad.engine.export.motion import clips

    size = _size(held, shown)
    baked = clips(view, targets, size) if motions else []
    animations = bake(view, held, shown, targets, size) if getattr(view.source, "animations", None) else []
    animated = sorted({index for clip in baked for index in clip.instances}
                      | {channel.instance for animation in animations for channel in animation.channels})
    target_of = {target.node: target for target in targets}
    for index in animated:
        node = nodes[index]
        target = target_of[index]
        local = np.asarray(node.pop("matrix", None) or np.eye(4).ravel(), dtype=float).reshape(4, 4).T
        node["translation"] = [float(value) for value in local[:3, 3]]
        node["rotation"] = [float(value) for value in quaternion(local)]
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
        # A scale keys a part's own node alone (``motion.chosen``): its reach is its part's.
        prototype = placed_at[target_of[index].members[0]].prototype
        if prototype not in reaches:
            points = np.asarray(held[prototype].positions, dtype=float).reshape(-1, 3)
            reaches[prototype] = float(np.max(np.linalg.norm(points, axis=1))) if len(points) else 0.0
        return reaches[prototype]

    def keyed(index: int, path: str, interpolation: str, times: np.ndarray, rows: np.ndarray,
              duration: float) -> tuple[str, np.ndarray, np.ndarray]:
        rows = _local_rows(path, interpolation, rows, target_of[index].within)
        if interpolation == "STEP":
            return interpolation, times, rows
        far = reach(index) if path == "scale" else 0.0
        key = (path, interpolation, duration, far, np.asarray(times, dtype=float).tobytes(),
               np.asarray(rows, dtype=float).tobytes())
        if key not in written:
            written[key] = linear(times, rows, interpolation, path, duration, far)
        return "LINEAR", *written[key]

    found = []

    def animation(name: str, duration: float, clip_kind: str,
                  tracks: list[tuple[int, str, str, np.ndarray, np.ndarray]]) -> None:
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
            channels.append({"sampler": shared[key], "target": {"node": index, "path": path}})
        found.append({"name": name, "channels": channels, "samplers": samplers,
                      "extras": {"cad": {"duration": duration, "kind": clip_kind}}})

    for clip in baked:
        if clip.instances:
            animation(clip.name, clip.duration, "motion", [
                (index, path, "CUBICSPLINE", clip.times, rows)
                for index, translations, rotations in zip(clip.instances, clip.translations, clip.rotations)
                for path, rows in (("translation", translations), ("rotation", rotations))])
    for baked_animation in animations:
        if baked_animation.channels:
            animation(baked_animation.name, baked_animation.duration, "animation", [
                (channel.instance, channel.path, channel.interpolation, channel.times, channel.values)
                for channel in baked_animation.channels])
    return found


def _tuple(value: Any) -> tuple | None:
    return tuple(value) if value is not None else None
