"""A GLB in Blender's scene (``cad.blender.load``): the import, each node's object, and the clips.

**Which object is which node.** Blender's importer names an object after its node; after the node's mesh,
camera or light when the node has no name (``Mesh_0``, ``Camera``), or ``Node_<index>`` for an empty; and
Blender changes a name already taken (``twin.001``) and cuts a long one short (at 255 bytes; at 63 before
Blender 5). So a name does not say which node an object is. Blender is therefore handed a copy of the file
whose JSON tags every node with its index in the node's ``extras`` -- which the importer keeps on the object
it makes of a node, as a custom property -- and names every animation by its index, so each action is found
by a name no other holds. The copy is a ``.gltf`` beside the GLB's binary chunk, in a temporary folder
removed once the import is done (the GLB itself is read by the library's own reader,
``cad.engine.formats.gltf``); the tags are then taken off the objects, and each action is given its clip's
name.

**Where a node stands.** A node a clip moves is put back where the file's own JSON places it, as the
importer places an object: glTF's Y up turned Z up (``_C``), and a camera's or a light's own object turned
once more, since Blender's look down their -Z where glTF's, turned, look along +Y. A node no clip moves is
left as imported.

**Clips.** Every action and NLA track the import made is cleared, and a clip is played by assigning its
action and slot to each object it moves (``Model.play``). A clip is a node's translation, rotation and
scale: morph weights are left as Blender imports them.
"""

from __future__ import annotations

import json
import math
import tempfile
import urllib.parse
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import bpy
from mathutils import Matrix, Quaternion, Vector

from cad.engine.formats.gltf import _chunks

__all__ = ["Clip", "Model", "load"]

# glTF is Y up and Blender Z up: the importer turns every node's placement by this (a quarter turn about
# X), as it turns the meshes, so a node's Blender placement is C @ M @ C^-1.
_C = Matrix.Rotation(math.pi / 2, 4, "X")
# The custom property a node's object carries its node's index in, until it is read.
_TAG = "cad_blender_node"
# What of a node a clip moves.
_MOVES = ("translation", "rotation", "scale")


@dataclass(frozen=True)
class Clip:
    """One of the GLB's animations: ``kind`` is ``motion`` (a configuration sequence) or ``animation`` (an
    ``animation()``), empty for a file cad did not write; ``duration`` in seconds."""

    name: str
    kind: str
    duration: float


@dataclass
class Model:
    """The imported model. ``root`` is the object of the scene's first root node (``roots``: of each, in the
    file's order). ``objects`` is each node's object by the node's name (in a GLB cad wrote, its path below the
    root, ``arm/head/pin_1``); a node with no name by the name Blender gave its object (``Mesh_0``,
    ``Node_3``); a name given twice, the last. ``nodes`` is each by its index in the file, which tells two of
    one name apart. ``clips`` by name, ``box`` the world box (low, high corners in metres) of the pose the file
    was written in, and ``clip`` the one playing."""

    root: bpy.types.Object
    roots: list
    objects: dict
    nodes: dict
    clips: dict
    box: tuple
    fps: int
    clip: str | None = None
    _made: list = field(default_factory=list, repr=False)
    _rest: dict = field(default_factory=dict, repr=False)
    _actions: dict = field(default_factory=dict, repr=False)

    @property
    def center(self) -> Vector:
        return (self.box[0] + self.box[1]) / 2

    @property
    def size(self) -> Vector:
        return self.box[1] - self.box[0]

    def play(self, name: str | None) -> None:
        """Play the clip ``name`` (None: no clip, every part where the file places it), the scene at its
        frame 0. The scene's range is the clip's, frames 0 to its duration at the model's fps."""
        if name is not None and name not in self.clips:
            raise KeyError(f"{name!r} is not a clip of this GLB: it has {sorted(self.clips) or 'none'}")
        for item, placed in self._rest.items():
            if item.animation_data:
                item.animation_data.action = None
            item.matrix_basis = placed
        scene = bpy.context.scene
        if name is not None:
            action, moved = self._actions[name]
            for item, slot in moved:
                data = item.animation_data or item.animation_data_create()
                data.action = action
                data.action_slot = slot
            scene.frame_start, scene.frame_end = 0, max(1, round(self.clips[name].duration * self.fps))
        self.clip = name
        scene.frame_set(0)

    def bounds(self) -> tuple:
        """The world box (low, high corners in metres) of every mesh at the scene's current frame."""
        return _box(self._made)


def load(path: str | Path, clip: str | None = None, fps: int = 24) -> Model:
    """Import the GLB at ``path`` into the current scene and play ``clip`` (None: stand still). ``fps`` is
    set before the import, which keys each clip's seconds at it. ``ValueError`` for a file that is no GLB,
    or one with no node."""
    path = Path(path)
    gltf, binary = _chunks(path)
    nodes = gltf.get("nodes") or []
    animations = gltf.get("animations") or []
    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = int(fps), 1.0
    before = {item.session_uid for item in bpy.data.objects}
    token = uuid.uuid4().hex[:12]
    _import(path, gltf, binary, token)
    made = [item for item in bpy.data.objects if item.session_uid not in before]

    by_node = {}
    for item in made:
        if _TAG in item:
            by_node[int(item[_TAG])] = item
            del item[_TAG]
    roots = [by_node[index] for index in _roots(gltf) if index in by_node]
    if not roots:
        raise ValueError(f"{path.name} has no node: there is nothing of it to place")
    objects = {nodes[index].get("name") or by_node[index].name: by_node[index] for index in sorted(by_node)}

    # Where the file places each node a clip moves.
    parents = {child: index for index, node in enumerate(nodes) for child in node.get("children") or ()}
    unit = 1.0 / scene.unit_settings.scale_length
    moved = {channel["target"]["node"] for animation in animations for channel in animation.get("channels") or ()
             if (channel.get("target") or {}).get("path") in _MOVES and "node" in channel["target"]}
    rest = {by_node[index]: _placed(nodes, index, parents.get(index), unit) for index in sorted(moved)
            if index in by_node}

    # Who each clip moves, read before anything is cleared: the live action and every NLA strip.
    slots: dict = {}
    for item in made:
        data = item.animation_data
        if data is None:
            continue
        pairs = [(data.action, data.action_slot)] + [(strip.action, strip.action_slot)
                                                     for track in data.nla_tracks for strip in track.strips]
        for action, slot in pairs:
            if action is not None and (item, slot) not in slots.setdefault(action.session_uid, []):
                slots[action.session_uid].append((item, slot))
        for track in list(data.nla_tracks):
            data.nla_tracks.remove(track)
        data.action = None

    clips, actions = {}, {}
    for index, animation in enumerate(animations):
        action = bpy.data.actions.get(_tagged_clip(token, index))
        if action is None:
            continue  # it moves no node Blender made an object of
        name = animation.get("name") or f"animation_{index}"
        action.name = name
        action.use_fake_user = True  # kept in a saved .blend while another clip plays
        said = (animation.get("extras") or {}).get("cad") or {}
        clips[name] = Clip(name, str(said.get("kind", "")), float(said.get("duration", action.frame_range[1] / fps)))
        actions[name] = (action, slots.get(action.session_uid, []))

    model = Model(roots[0], roots, objects, by_node, clips, (Vector(), Vector()), int(fps), None, made, rest, actions)
    model.play(None)
    model.box = model.bounds()
    if clip is not None:
        model.play(clip)
    return model


def _tagged_clip(token: str, index: int) -> str:
    """The name animation ``index`` is imported under: this load's alone."""
    return f"cad-{token}-{index}"


def _import(path: Path, gltf: dict[str, Any], binary: bytes, token: str) -> None:
    """Blender's importer run on a tagged copy of the GLB (see the module): every node's index in its
    ``extras``, every animation named by its index, the binary chunk a file beside the JSON."""
    tagged = dict(gltf)
    if gltf.get("nodes"):
        tagged["nodes"] = [
            {**node, "extras": {**(node["extras"] if isinstance(node.get("extras"), dict) else {}), _TAG: index}}
            for index, node in enumerate(gltf["nodes"])]
    if gltf.get("animations"):
        tagged["animations"] = [{**animation, "name": _tagged_clip(token, index)}
                                for index, animation in enumerate(gltf["animations"])]
    with tempfile.TemporaryDirectory(prefix="cad-blender-") as folder:
        buffers = []
        for buffer in gltf.get("buffers") or ():
            if "uri" not in buffer:  # the GLB's own chunk
                (Path(folder) / "scene.bin").write_bytes(binary)
                buffer = {**buffer, "uri": "scene.bin"}
            buffers.append(_beside(buffer, path))
        if buffers:
            tagged["buffers"] = buffers
        if gltf.get("images"):
            tagged["images"] = [_beside(image, path) for image in gltf["images"]]
        copy = Path(folder) / "scene.gltf"
        copy.write_text(json.dumps(tagged), encoding="utf-8")
        done = bpy.ops.import_scene.gltf(filepath=str(copy))
    if "FINISHED" not in done:
        raise RuntimeError(f"Blender did not import {path.name}")
    # The importer's own list of the clips it made, where its panel is registered: none is live here.
    tracks = getattr(bpy.data.scenes[0], "gltf2_animation_tracks", None)
    for at in reversed(range(len(tracks) if tracks is not None else 0)):
        if tracks[at].name.startswith(f"cad-{token}-"):
            tracks.remove(at)


def _beside(entry: dict[str, Any], path: Path) -> dict[str, Any]:
    """A buffer or an image whose file stands beside the GLB (a relative ``uri``), named by its whole path:
    the copy Blender reads is in another folder."""
    uri = entry.get("uri")
    if not uri or uri == "scene.bin" or urllib.parse.urlsplit(uri).scheme:
        return entry
    return {**entry, "uri": urllib.parse.quote(str((path.parent / urllib.parse.unquote(uri)).resolve()))}


def _roots(gltf: dict[str, Any]) -> list[int]:
    """The scene's root nodes, in the file's order; of a file with no scene, every node that is no node's
    child."""
    scenes = gltf.get("scenes") or []
    if scenes:
        return list(scenes[min(int(gltf.get("scene", 0)), len(scenes) - 1)].get("nodes") or ())
    nodes = gltf.get("nodes") or []
    children = {child for node in nodes for child in node.get("children") or ()}
    return [index for index in range(len(nodes)) if index not in children]


def _aimed(node: dict[str, Any]) -> bool:
    """Whether a node's own object is a camera or a light, which Blender aims along another axis than glTF: a
    node with a mesh keeps the mesh, and its camera or light is a child object of Blender's making."""
    return "mesh" not in node and ("camera" in node or "KHR_lights_punctual" in (node.get("extensions") or {}))


def _placed(nodes: list, index: int, parent: int | None, unit: float) -> Matrix:
    """Where the file places a node, as Blender's importer places its object (``matrix_basis``): the node's
    own transform turned Z up, in the scene's unit, with the turn a camera's or a light's object takes, and
    the one that undoes its parent's."""
    matrix = _C @ _local(nodes[index]) @ _C.inverted()
    matrix.translation = matrix.translation * unit
    if _aimed(nodes[index]):
        matrix = matrix @ _C
    if parent is not None and _aimed(nodes[parent]):
        matrix = _C.inverted() @ matrix
    return matrix


def _local(node: dict[str, Any]) -> Matrix:
    """A node's placement in its parent's frame, glTF's way: its matrix, else T @ R @ S."""
    if "matrix" in node:
        values = node["matrix"]  # column-major
        return Matrix([[values[column * 4 + row] for column in range(4)] for row in range(4)])
    x, y, z, w = node.get("rotation", (0.0, 0.0, 0.0, 1.0))
    scale = node.get("scale", (1.0, 1.0, 1.0))
    return (Matrix.Translation(node.get("translation", (0.0, 0.0, 0.0))) @ Quaternion((w, x, y, z)).to_matrix().to_4x4()
            @ Matrix.Diagonal((*scale, 1.0)))


def _box(objects: list) -> tuple:
    """The world box of the meshes among ``objects`` that the current view layer holds."""
    graph = bpy.context.evaluated_depsgraph_get()
    here = {item.session_uid for item in bpy.context.view_layer.objects}
    corners = [item.evaluated_get(graph).matrix_world @ Vector(corner)
               for item in objects if item.type == "MESH" and item.session_uid in here for corner in item.bound_box]
    if not corners:
        return Vector(), Vector()
    low = Vector(tuple(min(point[axis] for point in corners) for axis in range(3)))
    high = Vector(tuple(max(point[axis] for point in corners) for axis in range(3)))
    return low, high
