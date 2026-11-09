# cad_glb: a GLB that cad exported, imported into Blender as cad placed it.
# Copyright (c) 2026 Thompson Labs LLC
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# General Public License as published by the Free Software Foundation, either version 3 of the License,
# or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even
# the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
# License for more details.
#
# You should have received a copy of the GNU General Public License along with this program (COPYING,
# beside this file). If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# This is text-to-cad's only GPL file, and it runs only inside Blender (bpy); everything else is MIT.
"""Import a GLB that cad exported into the current Blender scene, every part where cad placed it.

    import cad_glb

    model = cad_glb.load("scene.glb", clip="explode", fps=24)
    model.root, model.box, model.clips      # the root empty, the world box in metres, each clip
    model.play("cycle")                     # another clip; model.play(None) stands still

Blender's glTF importer gets three things wrong with a file that has clips, and this fixes them:
it poses an animated node at its first clip's pose (so a still shows the wrong pose with no error);
only that first clip is live, and clearing it leaves its last pose; and keys start at frame 0. So
every action and NLA track the import made is cleared, every node is put back where the GLB's own
JSON places it, and a clip is played by assigning its action and slot to each object it moves,
the scene's frames 0 to its duration. Nothing of cad's is imported: bpy, mathutils and the
standard library alone.
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector

__all__ = ["Clip", "Model", "load"]

# glTF is Y up and Blender Z up: the importer turns every node's placement by this (a quarter turn
# about X), as it turns the meshes, so a node's Blender placement is C @ M @ C^-1.
_C = Matrix.Rotation(1.5707963267948966, 4, "X")
_SUFFIX = re.compile(r"\.\d{3}$")


@dataclass(frozen=True)
class Clip:
    """One of the GLB's animations: ``kind`` is ``motion`` (a configuration sequence) or
    ``animation`` (an ``animation()``), ``duration`` in seconds."""

    name: str
    kind: str
    duration: float


@dataclass
class Model:
    """The imported model: ``root`` is the document's root empty, ``objects`` each glTF node's object
    by its name (the node's path below the root, ``arm/head/pin_1``), ``clips`` by name, ``box`` the
    world box (low, high corners in metres) of the pose cad wrote, and ``clip`` the one playing."""

    root: bpy.types.Object
    objects: dict
    clips: dict
    box: tuple
    fps: int
    clip: str | None = None
    _placed: dict = field(default_factory=dict, repr=False)
    _actions: dict = field(default_factory=dict, repr=False)

    @property
    def center(self) -> Vector:
        return (self.box[0] + self.box[1]) / 2

    @property
    def size(self) -> Vector:
        return self.box[1] - self.box[0]

    def play(self, name: str | None) -> None:
        """Play the clip ``name`` (None: no clip, every part where cad placed it), the scene at its
        frame 0. The scene's range is the clip's, frames 0 to its duration at the model's fps."""
        if name is not None and name not in self.clips:
            raise KeyError(f"{name!r} is not a clip of this GLB: it has {sorted(self.clips) or 'none'}")
        for item in self.objects.values():
            if item.animation_data:
                item.animation_data.action = None
            item.matrix_basis = self._placed[item.name]
        scene = bpy.context.scene
        if name is not None:
            action = self._actions[name]
            for item, slot in action[1]:
                data = item.animation_data or item.animation_data_create()
                data.action = action[0]
                data.action_slot = slot
            scene.frame_start, scene.frame_end = 0, max(1, round(self.clips[name].duration * self.fps))
        self.clip = name
        scene.frame_set(0)

    def bounds(self) -> tuple:
        """The world box (low, high corners in metres) of every mesh at the scene's current frame."""
        return _box(self.objects.values())


def load(path: str | Path, clip: str | None = None, fps: int = 24) -> Model:
    """Import the GLB at ``path`` into the current scene and play ``clip`` (None: stand still).
    ``fps`` is set before the import, which keys each clip's seconds at it."""
    path = Path(path)
    gltf = _json(path)
    scene = bpy.context.scene
    scene.render.fps, scene.render.fps_base = int(fps), 1.0
    objects_before, actions_before = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=str(path))
    made = [item for item in bpy.data.objects if item not in objects_before]
    actions = [action for action in bpy.data.actions if action not in actions_before]

    nodes = gltf["nodes"]
    (top,) = gltf["scenes"][gltf.get("scene", 0)]["nodes"][:1]
    roots = [item for item in made if item.parent is None]
    root = _named(roots, nodes[top]["name"])
    objects, placed = {}, {}

    def walk(index: int, item: bpy.types.Object) -> None:
        node = nodes[index]
        objects[node["name"]] = item
        placed[item.name] = _C @ _local(node) @ _C.inverted()
        for child in node.get("children", ()):
            walk(child, _named(list(item.children), nodes[child]["name"]))

    walk(top, root)

    # Who each clip moves, read before anything is cleared: the live action and every NLA strip.
    moved: dict = {}
    for item in objects.values():
        data = item.animation_data
        if data is None:
            continue
        pairs = [(data.action, data.action_slot)] + [(strip.action, strip.action_slot)
                                                     for track in data.nla_tracks for strip in track.strips]
        for action, slot in pairs:
            if action is not None and (item, slot) not in moved.setdefault(action, []):
                moved[action].append((item, slot))
        for track in list(data.nla_tracks):
            data.nla_tracks.remove(track)
        data.action = None

    clips, by_clip = {}, {}
    for animation in gltf.get("animations", ()):
        name = animation.get("name") or f"animation_{len(clips)}"
        said = (animation.get("extras") or {}).get("cad") or {}
        action = _named(actions, name)
        action.use_fake_user = True  # kept in a saved .blend while another clip plays
        clips[name] = Clip(name, str(said.get("kind", "")), float(said.get("duration", action.frame_range[1] / fps)))
        by_clip[name] = (action, moved.get(action, []))

    model = Model(root, objects, clips, (Vector(), Vector()), int(fps), None, placed, by_clip)
    model.play(None)
    model.box = model.bounds()
    if clip is not None:
        model.play(clip)
    return model


def _json(path: Path) -> dict:
    """The GLB's JSON chunk: what the importer drops (``extras.cad``) and every node as written."""
    raw = path.read_bytes()
    magic, _, _ = struct.unpack_from("<4sII", raw, 0)
    length, kind = struct.unpack_from("<I4s", raw, 12)
    if magic != b"glTF" or kind != b"JSON":
        raise ValueError(f"{path} is not a GLB")
    return json.loads(raw[20:20 + length])


def _local(node: dict) -> Matrix:
    """A node's placement in its parent's frame, glTF's way: its matrix, else T @ R @ S."""
    if "matrix" in node:
        values = node["matrix"]  # column-major
        return Matrix([[values[column * 4 + row] for column in range(4)] for row in range(4)])
    x, y, z, w = node.get("rotation", (0.0, 0.0, 0.0, 1.0))
    scale = node.get("scale", (1.0, 1.0, 1.0))
    return (Matrix.Translation(node.get("translation", (0.0, 0.0, 0.0))) @ Quaternion((w, x, y, z)).to_matrix().to_4x4()
            @ Matrix.Diagonal((*scale, 1.0)))


def _named(candidates: list, name: str):
    """The one of ``candidates`` Blender gave ``name``: exactly, else with the ``.001`` it adds to a
    name already taken, else cut to its 63-byte limit."""
    for match in (lambda found: found == name, lambda found: _SUFFIX.sub("", found) == name,
                  lambda found: len(found.encode()) >= 59 and name.startswith(_SUFFIX.sub("", found))):
        found = [item for item in candidates if match(item.name)]
        if found:
            return found[0]
    raise LookupError(f"the import made nothing named {name!r}")


def _box(objects) -> tuple:
    graph = bpy.context.evaluated_depsgraph_get()
    corners = [item.evaluated_get(graph).matrix_world @ Vector(corner)
               for item in objects if item.type == "MESH" for corner in item.bound_box]
    if not corners:
        return Vector(), Vector()
    low = Vector(tuple(min(point[axis] for point in corners) for axis in range(3)))
    high = Vector(tuple(max(point[axis] for point in corners) for axis in range(3)))
    return low, high
