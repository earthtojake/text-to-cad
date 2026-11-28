"""The stills drawn by the view core's software renderer, where the kernel is the WebAssembly one.

A WebAssembly kernel carries no OpenGL, so its stills are drawn by the view core (its ``render`` job: a z-buffered
rasterizer held to OCCT's OpenGL picture, the job server's README, "The scene"). ``CoreScene`` is ``occt.Scene``
with the OCCT calls taken out: the same decisions -- what ``show`` shows (``Scene.plan``), the camera ``frame``
fits (``Scene.aim`` keeps it), the clip's plane and its caps' colours (``clip.cut``, ``clip.cap_colour``), the
grid's bands (``grid.drawn``), the ink's ribbons, lines and text quads (``Scene._ink``, ``_line``, ``_quad``) --
written as the core's scene, plain numbers and buffers, and drawn whole by the job each time the frame is asked
(``CoreCanvas.frame``). Nothing here imports the kernel: it runs in a Python that has none (the server's own),
beside the job server, a child process of its own (``Core``).

Preview is cad's own Preview code with the core under it (``Scene._studio``: its floor and the floor's shadow as
``triangles``, the shadow baked from the core's depth pictures, ``_depth``; ``_studio_backdrop``'s picture behind;
the key light's shadow map; the painter's tone mapping over frames the core draws). A GLB's base colour texture is
drawn on its faces (``texels``, ``texture``). What the core does not draw yet is refused in one line
(``NOT_YET``): the path tracer, Preview of a textured part, Preview seen from under its floor.
"""

from __future__ import annotations

import json
from collections import OrderedDict
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cad.engine.mesh_format import Mesh
from cad.engine.render.look import LOOK
from cad.engine.render.occt import BACKGROUND, EDGE, EDGES_WIN_OFFSET, SEE_THROUGH_OFFSET, Scene
from cad.engine.render.shapes import _LINE_OF, LINES, FaceGroup
from cad.engine.snapshot import SnapshotRefused

__all__ = ["NOT_YET", "Core", "CoreCanvas", "CoreScene", "CoreStopped", "NotDrawnYet", "TooLarge", "part_meshes",
           "samples_for"]

# Samples a pixel: what cad asks of OpenGL (a software OpenGL gives 4); fewer where a picture is so large that the
# core's cap on samples in all (``MOST_SAMPLES``) asks it (``samples_for``).
SAMPLES = 8
#: What the core draws at most: samples in all (8192 x 8192 at one sample, 4096 x 4096 at four) and pixels a side.
MOST_SAMPLES = 2**26
MOST_SIDE = 16384
#: The most a job's frame carries of the meshes it sends (the host takes a frame of up to 512 MiB): a still whose
#: meshes are more is sent over several frames, each mesh once, named by its key after (``Core.render``).
FRAME_BYTES = 256 * 2**20
# What the ink's presentations step back by in OCCT's depth test (its shaded aspect's polygon offset).
INK_OFFSET = (1.0, 1.0)

#: What the core does not draw yet, each refused in one line (``NotDrawnYet``) on the WebAssembly kernel.
NOT_YET = {
    "path-trace": "the path tracer does not run on the WebAssembly kernel: ask for the picture without it, or "
                  "choose the native kernel",
    "textures": "Preview of {name}'s base colour textures is not drawn on the WebAssembly kernel yet: ask for it "
                "without --preview, or choose the native kernel",
    "under": "Preview seen from under its floor is not drawn on the WebAssembly kernel yet: ask for a camera above "
             "the floor, or choose the native kernel",
}


class NotDrawnYet(SnapshotRefused):
    """What the view core's renderer does not draw yet (``NOT_YET``), asked of it: refused, as a request is."""


def samples_for(width: int, height: int) -> int:
    """The samples a pixel a still of ``width`` x ``height`` is drawn with: ``SAMPLES``, or the most of 4, 2 and 1 the
    core's cap (``MOST_SAMPLES``) allows; ``TooLarge`` where it allows none."""
    for samples in (SAMPLES, 4, 2, 1):
        if width * height * samples <= MOST_SAMPLES and max(width, height) <= MOST_SIDE:
            return samples
    raise TooLarge(f"a still {width} x {height} pixels as drawn is past what the WebAssembly kernel's renderer draws "
                   f"at once ({MOST_SAMPLES} pixels: 8192 x 8192): ask for a smaller size or renderScale", part="size")


class TooLarge(SnapshotRefused):
    """A still larger than the view core draws (``samples_for``)."""


class CoreStopped(SnapshotRefused):
    """A picture the view core's job server did not draw in time, or failed: the server stopped and started afresh
    for the next one; refused, in one line."""


# --- the job server ------------------------------------------------------------------------------------------


class Core:
    """The view core's job server (``program``: the kernel folder's ``bin/viewcore``), started on the first picture
    and kept as a child of this process, which it ends with. Each part's mesh crosses the pipe once: a buffer is sent
    under its key and named by it after (the ``render`` job's ``keys``); what the server says it no longer keeps is
    sent again."""

    def __init__(self, program: str) -> None:
        self.program = program
        self.child: subprocess.Popen | None = None
        self.sent: set[str] = set()  # the keys the running server was sent
        self.asked = 0
        self.faults = 0  # its module's faults running

    def _started(self) -> subprocess.Popen:
        if self.child is None or self.child.poll() is not None:
            from cad.engine import places

            self.child = subprocess.Popen([self.program], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          **places.windowless())
            self.sent = set()
        return self.child

    def job(self, header: dict[str, Any], payloads: list[bytes]) -> tuple[dict[str, Any], list[bytes]]:
        """``header`` and ``payloads`` asked of the server within its job's deadline (``core_pool.exchange``): its
        answer's header and payloads. A job it refuses is a ``RuntimeError`` in its words; a server that is late,
        ends or answers what is no frame is killed (the next job starts another, sent again what it keeps) and the job
        refused in one line (``CoreStopped``); so is a job its module faulted on, the server having started its module
        again and let go of what it kept, and one that faults ``core_pool.FAULTS`` times running is killed too."""
        from cad.engine.core_pool import FAULTS, HostFailed, _killed, exchange, faulted

        child = self._started()
        self.asked += 1
        try:
            said, found = exchange(child, {**header, "id": self.asked}, payloads)
        except HostFailed as failed:
            self.child, self.sent = None, set()
            raise CoreStopped(str(failed)) from None
        if faulted(said):
            self.sent, self.faults = set(), self.faults + 1  # what it kept is gone with its module
            if self.faults >= FAULTS:
                _killed(child)
                self.child, self.faults = None, 0
            raise CoreStopped(f"{said.get('error')}: ask again")
        self.faults = 0
        if not said.get("ok"):
            raise RuntimeError(f"the view core refused the {header.get('job')} job: {said.get('error')}")
        return said, found

    def render(self, scene: dict[str, Any], payloads: list[bytes], keys: list[str | None]) -> tuple[bytes, float]:
        """The picture ``scene`` describes (its payloads in order, each named by its key or None): its bytes as the
        scene's ``format`` asks, and the seconds the core drew for. A keyed buffer the server keeps is named, not sent;
        one it says it lacks is sent again; and buffers past ``FRAME_BYTES`` in a frame wait for the next, the server
        keeping each sent meanwhile."""
        for _turn in range(len(payloads) + 2):
            sending, room, fresh = [], FRAME_BYTES, []
            for key, data in zip(keys, payloads):
                if key is not None and key in self.sent:
                    sending.append(b"")
                elif key is None or len(data) <= room or not fresh:
                    sending.append(data)
                    room -= len(data)
                    if key is not None:
                        fresh.append(key)
                else:
                    sending.append(b"")  # named only: sent in the next frame
            said, found = self.job({"job": "render", "scene": scene, "keys": keys}, sending)
            self.sent.update(fresh)
            if "missing" not in said:
                return found[0], float(said.get("seconds") or 0.0)
            self.sent.difference_update(said["missing"])
            if set(fresh) & set(said["missing"]):
                break  # it let go of what this very frame sent it: it cannot hold them all at once
        raise CoreStopped("the view core could not keep this still's meshes at once (they are more than it holds): "
                          "ask for fewer parts")

    def stop(self) -> None:
        """The server ended (its input closed), if it runs."""
        child, self.child = self.child, None
        self.sent = set()
        if child is None:
            return
        try:
            child.stdin.close()
            child.wait(5)
        except (OSError, subprocess.TimeoutExpired):
            child.kill()
            child.wait()
        child.stdout.close()


# --- a part, as the core draws it ------------------------------------------------------------------------------


@dataclass
class PartMesh:
    """A part as ``shapes.PartShapes`` holds it, for the core: each face group's index ranges in the part's mesh
    (``[[first, count]...]``, or None for all of them), the edge classes it has, each group's material."""

    faces: dict[Any, list[list[int]] | None] = field(default_factory=dict)
    edges: dict[str, bool] = field(default_factory=dict)
    materials: dict[Any, Any] = field(default_factory=dict)
    textures: dict[Any, Any] = field(default_factory=dict)  # group: its texture set (a GLB's, read by the kernel)
    uvs: Any = None  # each node's texture coordinates, where the part has textures


def _ranges(rows: np.ndarray, chosen: np.ndarray) -> list[list[int]]:
    """The index ranges of the face table's ``rows`` (ordinal, first, count) that ``chosen`` marks, runs joined."""
    found: list[list[int]] = []
    for _ordinal, first, count in rows[chosen & (rows[:, 2] > 0)].tolist():
        if found and found[-1][0] + found[-1][1] == first:
            found[-1][1] += count
        else:
            found.append([first, count])
    return found


def part_meshes(prototype: dict[str, Any], mesh: Mesh) -> PartMesh:
    """``shapes.prototype_shapes`` for the core: the same groups, in the same order (the part's own faces, then each
    paint by its colour and material), as ranges of the mesh's triangles; the edge classes with a polyline."""
    colors = prototype.get("faceColors") or {}
    materials = prototype.get("faceMaterials") or {}
    group_of: dict[int, FaceGroup] = {}
    group_materials: dict[Any, Any] = {}
    for ordinal in set(colors) | set(materials):
        material = materials.get(ordinal)
        raw = colors.get(ordinal)
        key = None if material is None else json.dumps(material, sort_keys=True, separators=(",", ":"), allow_nan=False)
        group = FaceGroup(tuple(raw) if raw is not None else None, key)
        group_of[int(ordinal)] = group
        if material is not None:
            group_materials[group] = material
    rows = np.asarray(mesh.faces, np.int64).reshape(-1, 3)
    found = PartMesh(materials=group_materials)
    if not group_of:
        if len(mesh.indices):
            found.faces[None] = None
    else:
        ordinals = rows[:, 0]
        painted = np.array([int(o) in group_of for o in ordinals.tolist()], bool)
        found.faces[None] = _ranges(rows, ~painted)
        for group in sorted(set(group_of.values()), key=str):
            mine = np.array([group_of.get(int(o)) == group for o in ordinals.tolist()], bool)
            found.faces[group] = _ranges(rows, mine)
        found.faces = {group: ranges for group, ranges in found.faces.items() if ranges}  # none without triangles
    edges = np.asarray(mesh.edges, np.int64).reshape(-1, 4)
    edges = edges[edges[:, 2] >= 2]
    for line in LINES:
        if np.isin(edges[:, 3], [c for c, n in _LINE_OF.items() if n == line]).any():
            found.edges[line] = True
    return found


# --- the scene -------------------------------------------------------------------------------------------------


class _Payloads:
    """A scene's buffers in the order it names them, each by its place: a keyed one (a part's mesh, the
    environment) once."""

    def __init__(self) -> None:
        self.data: list[bytes] = []
        self.keys: list[str | None] = []
        self._at: dict[str, int] = {}

    def add(self, data: bytes, key: str | None = None) -> int:
        if key is not None and key in self._at:
            return self._at[key]
        self.data.append(data)
        self.keys.append(key)
        if key is not None:
            self._at[key] = len(self.data) - 1
        return len(self.data) - 1

    def array(self, values: Any, dtype: str) -> int:
        return self.add(np.ascontiguousarray(values, dtype).tobytes())


def _linear(value: Any) -> list[float]:
    from cad.engine.render.finish import linear

    return [float(c) for c in linear(value)]


class CoreCanvas:
    """What a ``CoreScene`` is drawn on: its size, and its frame drawn by the core whole each time it is asked."""

    def __init__(self, scene: "CoreScene", width: int, height: int) -> None:
        self.scene, self.width, self.height = scene, width, height
        self.seconds = 0.0  # what the core drew the last frame in

    def frame(self, *, text: bool = True) -> np.ndarray:
        """The scene drawn, as sRGB bytes (height, width, 3); ``text`` off: without its text marks."""
        scene, payloads, keys = self.scene.describe(text=text)
        data, self.seconds = self.scene.core.render(scene, payloads, keys)
        return np.frombuffer(data, np.uint8).reshape(self.height, self.width, 4)[..., :3].copy()

    def png(self, paint: Any = None) -> bytes:
        from cad.engine.render.context import encode

        frame = self.frame()
        if paint is not None:
            paint(frame)
        return encode(frame)

    def save(self, path: str, paint: Any = None) -> float:
        started = time.perf_counter()
        data = self.png(paint)
        with open(path, "wb") as handle:
            handle.write(data)
        return time.perf_counter() - started

    def close(self) -> None:
        """Nothing is held for a frame: the job server is its ``Core``'s."""


class CoreScene(Scene):
    """``occt.Scene`` drawn by the view core (``core``, a ``Core``): the scene's decisions as they are, its OCCT
    presentations a draw list the core is handed for each frame."""

    def __init__(self, path: Any, buffers: dict[str, bytes], *, core: Core, **given: Any) -> None:
        self.core = core
        self.buffers = buffers  # each part's mesh as the core is sent it
        self.ink: list[tuple[Any, ...]] = []  # the annotation's ribbons, lines and text quads, as made
        self.cut: list[float] | None = None  # the clip's plane, [a, b, c, d]: what is kept is where ax+by+cz+d >= 0
        self.backdrop_picture: np.ndarray | None = None  # Preview's backdrop: the row OCCT shows (``_behind``)
        self.grid_bands: Any = None
        super().__init__(path, buffers, **given)

    # --- what OCCT did, done as the core takes it -------------------------------------------------------------

    def _canvas(self, size: tuple[int, int]) -> CoreCanvas:
        return CoreCanvas(self, *size)

    @staticmethod
    def _part(prototype: dict[str, Any], mesh: Mesh) -> PartMesh:
        return part_meshes(prototype, mesh)

    def _setup_view(self) -> None:
        self.lights = []

    def _rig(self, colour_only: bool) -> None:
        self.colour_only = colour_only

    def _take_down(self) -> None:
        self.shown = []

    def _put_up(self, plan: list[tuple[str, int, int, Any, Any]], look: str) -> None:
        self.shown = list(plan)
        self.look_shown = look

    def _clip(self, clip: dict[str, Any] | None) -> None:
        """``clip.apply`` for the core: the plane, and a cap for each instance shown (none in Wireframe)."""
        from cad.engine.render import clip as section

        self.caps, self.cut = [], None
        if not clip or clip.get("enabled") is False:
            return
        normal, point = section.cut(self, clip)
        self.cut = [*map(float, normal), -float(np.dot(normal, point))]
        if self.mode == "wireframe":
            return
        for index, instance in enumerate(self.structure["instances"]):
            p = instance["prototype"]
            if index in self.hidden or not len(self.meshes[self.prototypes[p]["key"]].indices):
                continue
            cap = ("cap", index, p, None, section.cap_colour(self, index, clip))
            self.caps.append(cap)
            self.shown.append(cap)

    def aim(self, camera: dict[str, Any]) -> dict[str, Any]:
        self.camera = camera  # the core fits near and far to what it draws
        if self.studio:
            self._studio_backdrop()  # the sweep's shading follows the camera
        return camera

    def project(self, points: np.ndarray) -> np.ndarray:
        """World points to output pixels (x right, y down), through the camera as the core draws by it."""
        camera = self.camera
        eye, target = np.asarray(camera["eye"], float), np.asarray(camera["target"], float)
        back = (eye - target) / np.linalg.norm(eye - target)
        right = np.cross(np.asarray(camera["up"], float), back)
        right /= np.linalg.norm(right)
        up = np.cross(back, right)
        v = np.asarray(points, float).reshape(-1, 3) - eye
        x, y = v @ right, v @ up
        width, height = self.canvas.width, self.canvas.height
        if camera["projection"] == "perspective":
            focal = (height / 2) / np.tan(np.radians(camera["fov"]) / 2)
            depth = -(v @ back)
            return np.column_stack([width / 2 + focal * x / depth, height / 2 - focal * y / depth])
        pixel = camera["scale"] / height
        return np.column_stack([width / 2 + x / pixel, height / 2 - y / pixel])

    def grid(self, on: bool = True) -> float:
        from cad.engine.render import grid

        clock = time.perf_counter()
        self.grid_bands = grid.drawn(self) if on and not self.preview else None
        return time.perf_counter() - clock

    def _ink(self, nodes: np.ndarray, triangles: np.ndarray, color: str) -> None:
        self.ink.append(("triangles", np.asarray(nodes, float), np.asarray(triangles), color))

    def _line(self, points: np.ndarray, color: str, width: float, closed: bool) -> None:
        points = np.asarray(points, float)
        self.ink.append(("line", np.vstack([points, points[:1]]) if closed else points, color, width))

    def _quad(self, corners: np.ndarray, picture: np.ndarray) -> None:
        self.ink.append(("text", np.asarray(corners, float), np.ascontiguousarray(picture, np.uint8)))

    def clear_overlays(self, keep: Any = ()) -> None:
        self.overlays, self.ink = [], []
        self.text_quads, self.screen_marks, self.fonts = [], [], set()

    def backdrop(self, colour: Any = None) -> None:
        self.behind = None if colour is None else tuple(colour)

    def _bare(self, boxes: list[tuple[int, int, int, int]]) -> list[np.ndarray]:
        """Each box of the frame drawn without the text quads: the whole frame drawn once so, cut up."""
        bare = self.canvas.frame(text=False)
        return [bare[y0:y1, x0:x1] for x0, y0, x1, y1 in boxes]

    def preview_look(self, path_trace: int = 0) -> float:
        """Preview's look (``Scene.preview_look``): its rig (the key casting its shadow, the studio's environment at
        full strength, ``describe``), its studio (the floor and its shadow, ``_studio``) and its backdrop."""
        if path_trace:
            raise NotDrawnYet(NOT_YET["path-trace"])
        clock = time.perf_counter()
        self._studio()
        self.studio, self.traced = True, False
        self._studio_backdrop()
        return time.perf_counter() - clock

    def path_trace(self, out: Any, samples: int) -> float:
        raise NotDrawnYet(NOT_YET["path-trace"])

    def _stage(self, nodes: list[tuple], triangles: list[tuple], *, colours: list[tuple] | None = None,
               texels: list[tuple] | None = None, picture: np.ndarray | None = None, below: bool = False) -> None:
        self.stage.append(_Staged(nodes, triangles, colours, texels, picture, below))

    def _behind(self, picture: np.ndarray) -> None:
        # OCCT stretches a background picture over the view reading its first texture row (v = 0), the picture's
        # last, at every pixel: that row, the same all the way down.
        self.backdrop_picture = np.ascontiguousarray(np.asarray(picture, np.uint8)[-1:, :, :3])

    def _through(self) -> np.ndarray | None:
        if self._under_floor():
            raise NotDrawnYet(NOT_YET["under"])
        return None

    def _depth(self, eye: Any, target: Any, up: Any, scale: float, size: int, z_range: Any = None,
               keep_above: float | None = None) -> np.ndarray:
        """``Scene._depth`` by the core: the model's depth from an orthographic camera, a sample a pixel, as OCCT
        reads it back (``occt_depth``). OCCT draws the square picture at the view's own aspect, the scale spanning
        its height (its width where the view is taller than wide), so the model is squeezed by that aspect along
        the camera's other side, as OCCT squeezes it into the square."""
        aspect = self.canvas.width / self.canvas.height
        back = np.asarray(eye, float) - np.asarray(target, float)
        back /= np.linalg.norm(back)
        right = np.cross(np.asarray(up, float), back)
        right /= np.linalg.norm(right)
        axis, squeeze = (right, 1 / aspect) if aspect >= 1 else (np.cross(back, right), aspect)
        squeezed = np.eye(4)
        squeezed[:3, :3] += (squeeze - 1) * np.outer(axis, axis)
        squeezed[:3, 3] = (np.eye(3) - squeezed[:3, :3]) @ np.asarray(target, float)
        found, payloads, keys = self.describe(placement=lambda index: squeezed @ self.placement(index), model=True)
        camera = {"projection": "orthographic", "eye": [float(v) for v in eye], "target": [float(v) for v in target],
                  "up": [float(v) for v in up], "height": float(scale)}
        if z_range is not None:
            camera["near"], camera["far"] = float(z_range[0]), float(z_range[1])
        found.update(width=size, height=size, samples=1, format="depth", camera=camera)
        if keep_above is not None:  # z >= keep_above, where the model was squeezed
            normal = np.linalg.solve(squeezed[:3, :3].T, [0.0, 0.0, 1.0])
            point = squeezed[:3, :3] @ [0.0, 0.0, float(keep_above)] + squeezed[:3, 3]
            found["clip"] = [*map(float, normal), -float(normal @ point)]
        data, _seconds = self.core.render(found, payloads, keys)
        return occt_depth(np.frombuffer(data, np.float32).reshape(size, size))

    def save(self, out: Any) -> float:
        return self.canvas.save(str(out), self.painter())

    # --- the scene the core draws ---------------------------------------------------------------------------

    def describe(self, *, text: bool = True, model: bool = False,
                 placement: Any = None) -> tuple[dict[str, Any], list[bytes], list[str | None]]:
        """The frame as the core's ``render`` job takes it (shown, framed): the scene, its payloads in order and each
        one's key (a part's mesh by its geometry key, the environment by its name; else None). ``text`` off: the
        text marks left out (``_bare``); ``model``: the model alone (no studio, grid or ink: a depth picture's),
        placed by ``placement`` where given."""
        from cad.engine.render import finish

        payloads = _Payloads()
        mesh_at: dict[int, int] = {}
        meshes: list[int] = []

        def mesh(p: int) -> int:
            if p not in mesh_at:
                key = self.prototypes[p]["key"]
                mesh_at[p] = len(meshes)
                meshes.append(payloads.add(self._buffer(key), f"mesh:{key}"))
            return mesh_at[p]

        placements: list[bytes] = []
        placed_at: dict[int, int] = {}

        placing = placement or self.placement

        def placed(index: int) -> int:
            if index not in placed_at:
                placed_at[index] = len(placements)
                placements.append(np.ascontiguousarray(placing(index).T, "<f8").tobytes())
            return placed_at[index]

        look, mode = self.look(), self.mode
        backdrop = _linear(self.background or BACKGROUND)
        layer = "topmost" if mode in ("xray", "wireframe") else "default"
        draw: list[dict[str, Any]] = []
        for kind, index, p, which, color in self.shown:
            if kind == "faces":
                draw.append(self._faces_draw(p, which, color, look, backdrop, mesh(p), placed(index), payloads))
            elif kind == "edges":
                draw.append({"edges": mesh(p), "classes": sorted(c for c, n in _LINE_OF.items() if n == which),
                             "matrix": placed(index), "color": _linear(EDGE[which]), "width": LOOK.edge_width,
                             "layer": layer})
            else:
                draw.append({"cap": mesh(p), "matrix": placed(index), "color": [float(c) for c in color]})
        if not model:
            if self.grid_bands is not None and len(self.grid_bands.triangles):
                draw.append(self._grid_draw(payloads))
            for item in self.ink:
                if item[0] == "text" and not text:
                    continue
                draw.append(self._ink_draw(item, payloads))
            # OCCT draws a layer's structures by display priority: the floor (below) before the model, the shadow after.
            shown = [staged for staged in self.stage if staged.shown]
            draw = ([staged.item(payloads) for staged in shown if staged.below] + draw
                    + [staged.item(payloads) for staged in shown if not staged.below])
        found: dict[str, Any] = {
            "width": self.canvas.width, "height": self.canvas.height,
            "samples": samples_for(self.canvas.width, self.canvas.height), "format": "rgba",
            "background": [float(c) for c in self.behind] if self.behind is not None else backdrop,
            "camera": self._camera_of(),
        }
        if self.studio and self.behind is None and self.backdrop_picture is not None:
            picture = self.backdrop_picture
            found["backdrop"] = {"payload": payloads.add(picture.tobytes()), "width": picture.shape[1],
                                 "height": picture.shape[0]}
        if self.studio:
            found["light"] = _preview_light(payloads)
        elif look == "xray":
            found["phong"] = {"ambient": LOOK.xray.ambient, "specular": LOOK.xray.specular,
                              "shininess": LOOK.xray.shininess,
                              "lights": [{"direction": list(light.direction), "intensity": light.intensity}
                                         for light in LOOK.xray.lights]}
        else:
            radiance = finish.environment()
            found["light"] = {
                "lights": [{"direction": list(light.direction), "intensity": light.intensity} for light in LOOK.lights],
                "environment": {"payload": payloads.add(_radiance(), "environment:look"), "width": radiance.shape[1],
                                "height": radiance.shape[0], "intensity": LOOK.environment.intensity}}
        if self.cut is not None:
            found["clip"] = list(self.cut)
        found["meshes"] = meshes
        found["matrices"] = payloads.add(b"".join(placements))
        found["draw"] = draw
        return found, payloads.data, payloads.keys

    def _buffer(self, key: str) -> bytes:
        return self.buffers[key]

    def _camera_of(self) -> dict[str, Any]:
        camera = self.camera
        found = {"projection": camera["projection"], "eye": [float(v) for v in camera["eye"]],
                 "target": [float(v) for v in camera["target"]], "up": [float(v) for v in camera["up"]]}
        if camera["projection"] == "perspective":
            found["fov"] = float(camera["fov"])
        else:
            found["height"] = float(camera["scale"])
        return found

    def _faces_draw(self, p: int, group: Any, color: Any, look: str, backdrop: list[float], mesh: int,
                    matrix: int, payloads: _Payloads) -> dict[str, Any]:
        """A face group's draw: ``Scene._faces``'s presentation in the core's numbers."""
        from cad.engine.render import finish

        ranges = self.parts[p].faces[group]
        item: dict[str, Any] = {"faces": mesh, "matrix": matrix, "layer": "default"}
        if ranges is not None:
            item["ranges"] = ranges
        fill = isinstance(color, str)
        if look == "hidden":
            item.update(shading="unlit", color=backdrop, alpha=1.0)
        elif look == "xray":
            base = finish.linear(color if color is not None else LOOK.fill)
            item.update(shading="phong", color=[float(c) for c in base], alpha=LOOK.mode("xray").opacity)
        elif look == "pbr" and (fill or self._material_of(p, group) is None):
            # Preview's surface without a material (``Scene._material``): its colour as it is, opaque, OCCT's default
            # PBR material at normalized roughness 0.5.
            base = finish.linear(color if color is not None else LOOK.fill)
            item.update(shading="pbr", color=[float(c) for c in base], alpha=1.0, metallic=0.0,
                        roughness=0.01 + 0.99 * 0.5, ior=1.5, emission=[0.0, 0.0, 0.0])
        else:
            own = None if fill else self._material_of(p, group)
            if fill:  # a fill (Parts) keeps the part's opacity, as the viewer's does
                part = self.prototypes[p].get("color") or ()
                color = (*finish.linear(color), float(part[3]) if len(part) > 3 else 1.0)
            made = finish.finish(color, own)
            item.update(shading="pbr", color=[float(c) for c in made["color"]], alpha=float(made["alpha"]),
                        metallic=float(made["metallic"]), roughness=float(made["roughness"]), ior=float(made["ior"]),
                        emission=[float(c) for c in made["emission"]])
        part = self.parts[p]
        texture = part.textures.get(group) if look in ("lit", "pbr") and not fill else None
        if texture is not None and part.uvs is not None:  # a GLB's base colour texture over its colour
            key = self.prototypes[p]["key"]
            picture = _texture_picture(texture)
            item["texels"] = payloads.add(np.ascontiguousarray(part.uvs, "<f4").tobytes(), f"texels:{key}")
            item["texture"] = {"payload": payloads.add(picture.tobytes(), f"texture:{key}:{group}"),
                               "width": picture.shape[1], "height": picture.shape[0]}
        see_through = look == "xray" or (look != "hidden" and item["alpha"] < 1)
        item["offset"] = list(SEE_THROUGH_OFFSET if see_through else EDGES_WIN_OFFSET)
        return item

    def _grid_draw(self, payloads: _Payloads) -> dict[str, Any]:
        """The grid's bands (``grid._present``): its profile texture, blended, stepped back as a face, never cut."""
        from cad.engine.render import grid as paper

        bands = self.grid_bands
        picture = _profile()
        return {"triangles": {"positions": payloads.array(bands.points, "<f4"),
                              "texels": payloads.array(bands.texels, "<f4"),
                              "indices": payloads.array(bands.triangles, "<u4")},
                "texture": {"payload": payloads.add(picture.tobytes(), f"grid:{LOOK.backdrop}:{paper.ACROSS}"),
                            "width": picture.shape[1], "height": picture.shape[0]},
                "color": [1.0, 1.0, 1.0, 1.0], "blend": True, "offset": [1.0, 1.0], "clip": False, "layer": "default"}

    @staticmethod
    def _ink_draw(item: tuple[Any, ...], payloads: _Payloads) -> dict[str, Any]:
        """A mark of the ink in the Top layer: tested against the model's depth, writing none, cut by the clip."""
        kind = item[0]
        if kind == "triangles":
            _kind, nodes, triangles, color = item
            return {"triangles": {"positions": payloads.array(nodes, "<f4"), "indices": payloads.array(triangles, "<u4")},
                    "color": [*_linear(color), 1.0], "blend": False, "offset": list(INK_OFFSET), "clip": True,
                    "layer": "top"}
        if kind == "line":
            _kind, points, color, width = item
            return {"lines": {"positions": payloads.array(points, "<f4"),
                              "counts": payloads.array([len(points)], "<u4")},
                    "color": _linear(color), "width": float(width), "clip": True, "layer": "top"}
        _kind, corners, picture = item  # a text mark: its canvas on its quad, three's uv, blended by its alpha
        return {"triangles": {"positions": payloads.array(corners, "<f4"),
                              "texels": payloads.array([[0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]], "<f4"),
                              "indices": payloads.array([[0, 1, 2], [0, 2, 3]], "<u4")},
                "texture": {"payload": payloads.add(picture.tobytes()), "width": picture.shape[1],
                            "height": picture.shape[0]},
                "color": [1.0, 1.0, 1.0, 1.0], "blend": True, "offset": list(INK_OFFSET), "clip": True, "layer": "top"}


class _Staged:
    """A presentation of Preview's studio (``Scene._stage``), kept for the core: shown or put away as the scene puts
    its structures away, drawn as an unlit, blended ``triangles`` draw, never cut, kept out of the near plane's fit."""

    def __init__(self, nodes: list[tuple], triangles: list[tuple], colours: list[tuple] | None,
                 texels: list[tuple] | None, picture: np.ndarray | None, below: bool) -> None:
        self.nodes = np.asarray(nodes, np.float32)
        self.triangles = np.asarray(triangles, np.uint32)
        self.colours = None if colours is None else np.asarray(colours, np.uint8)
        self.texels = None if texels is None else np.asarray(texels, np.float32)
        self.picture = None if picture is None else np.asarray(picture, np.uint8)
        self.below, self.shown = below, True

    def Erase(self) -> None:  # noqa: N802 - OCCT's structure's words, which the scene's Preview code calls
        self.shown = False

    def Remove(self) -> None:  # noqa: N802
        self.shown = False

    def Display(self) -> None:  # noqa: N802
        self.shown = True

    def item(self, payloads: _Payloads) -> dict[str, Any]:
        found: dict[str, Any] = {"positions": payloads.array(self.nodes, "<f4"),
                                 "indices": payloads.array(self.triangles, "<u4")}
        item: dict[str, Any] = {"triangles": found, "color": [1.0, 1.0, 1.0, 1.0], "blend": True, "offset": [1.0, 1.0],
                                "clip": False, "infinite": True, "layer": "default"}
        if self.colours is not None:
            found["colors"] = payloads.array(self.colours, "u1")
        if self.texels is not None:
            found["texels"] = payloads.array(self.texels, "<f4")
        if self.picture is not None:
            picture = self.picture if self.picture.shape[2] == 4 else np.concatenate(
                [self.picture, np.full(self.picture.shape[:2] + (1,), 255, np.uint8)], -1)
            item["texture"] = {"payload": payloads.array(picture, "u1"), "width": picture.shape[1],
                               "height": picture.shape[0]}
        return item


def _preview_light(payloads: _Payloads) -> dict[str, Any]:
    """``Scene.preview_look``'s rig as the core's light: the key (its direction, its strength, the shadow map it casts
    at 4096 texels with a bias of 0.002) and the environment at full strength, baked as ``STUDIO_BAKE`` asks."""
    from cad.engine.render import finish
    from cad.engine.render.occt import KEY_DIRECTION, KEY_ILLUMINANCE, STUDIO_BAKE

    radiance = finish.environment()
    key = -np.asarray(KEY_DIRECTION, float) / np.linalg.norm(KEY_DIRECTION)
    return {"lights": [{"direction": [float(v) for v in key], "intensity": KEY_ILLUMINANCE,
                        "shadow": {"resolution": 4096, "bias": 0.002}}],
            "environment": {"payload": payloads.add(_radiance(), "environment:look"), "width": radiance.shape[1],
                            "height": radiance.shape[0], "intensity": 1.0,
                            "specularSize": STUDIO_BAKE["PbrEnvPow2Size"],
                            "specularSamples": STUDIO_BAKE["PbrEnvBakingSpecNbSamples"]}}


def occt_depth(depth: np.ndarray) -> np.ndarray:
    """A depth picture as ``Scene._depth`` reads OCCT's back: the 8-bit picture OCCT dumps a depth into (stretched
    from its least to its most, ``(BYTE)(scale * (value - least) + 0.5)``), the two ends read as floats where the
    bytes are least and most, and the bytes put back between them."""
    least, most = float(depth.min()), float(depth.max())
    if most == least:
        least, most = 0.0, 255.0
    scale = 255.0 / (most - least)
    levels = np.floor(scale * (depth - np.float32(least)).astype(np.float64) + 0.5).astype(np.uint8).astype(np.float64)
    low_at, high_at = np.unravel_index(levels.argmin(), levels.shape), np.unravel_index(levels.argmax(), levels.shape)
    low, high = float(depth[low_at]), float(depth[high_at])
    return low + levels / 255.0 * (high - low)


# The textures' pictures read last (``_texture_picture``), each by its texture set, the least recently read let go of
# first: a render process draws one document's few textures again and again, and holds no more than these.
PICTURES = 32
_PICTURES: "OrderedDict[int, tuple[Any, np.ndarray]]" = OrderedDict()


def _texture_picture(texture: Any) -> np.ndarray:
    """A texture set's first texture (the base colour's) as RGBA bytes, the top row first (``_read_picture``), kept
    for the next frame among the last ``PICTURES`` read."""
    found = _PICTURES.get(id(texture))
    if found is not None and found[0] is texture:
        _PICTURES.move_to_end(id(texture))
        return found[1]
    picture = _read_picture(texture)
    _PICTURES[id(texture)] = (texture, picture)
    while len(_PICTURES) > PICTURES:
        _PICTURES.popitem(last=False)
    return picture


def _read_picture(texture: Any) -> np.ndarray:
    """The image OCCT reads of a texture set (a GLB's, which only the kernel reads: where there is a texture, there is
    a kernel)."""
    from OCP.Image import Image_SupportedFormats

    image = texture.First().GetImage(Image_SupportedFormats())
    height, width = image.SizeY(), image.SizeX()
    picture = np.zeros((height, width, 4), np.uint8)
    for y in range(height):
        for x in range(width):
            colour = image.PixelColor(x, y, False)
            rgb = colour.GetRGB()
            picture[y, x] = [round(rgb.Red() * 255), round(rgb.Green() * 255), round(rgb.Blue() * 255),
                             round(colour.Alpha() * 255)]
    return picture


_KEPT: dict[Any, Any] = {}


def _radiance() -> bytes:
    """The look's environment as the core takes it: float32 RGB rows, +Z at the top (``finish.environment``)."""
    if "radiance" not in _KEPT:
        from cad.engine.render import finish

        _KEPT["radiance"] = np.ascontiguousarray(finish.environment(), "<f4").tobytes()
    return _KEPT["radiance"]


def _profile() -> np.ndarray:
    """The grid's profile texture as bytes, cut short as OCCT's pixmap takes a colour (``grid.profile_texture``)."""
    if "profile" not in _KEPT:
        from cad.engine.render import grid

        _KEPT["profile"] = (np.clip(grid.profile(LOOK.backdrop), 0, 1) * 255.0).astype(np.uint8)
    return _KEPT["profile"]
