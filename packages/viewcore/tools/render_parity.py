"""The view core's stills, held against the pictures cad's OpenGL renderer draws from the same inputs.

    python tools/render_parity.py reference --out DIR FILE.xbf [...]       # needs a display: xvfb-run -a
    python tools/render_parity.py compare --out DIR [--native LIB.so] [--node NODE] [--wasm dist/viewcore.wasm]

Run with cad's environment (numpy, Pillow; ``reference`` also cad's renderer on the native kernel).

``reference`` draws each file in a set of cases (every display mode, three cameras, a clip, the grid, two sizes) with
``cad.engine.render.occt.Scene`` and writes, per case, the picture OCCT drew (``<case>.occt.png``) and the scene the
view core is to draw from (``<case>.json``, its payloads kept once in ``payloads/``): ``scene_of`` says in plain
Python what ``Scene.show``, ``Scene.frame``, ``clip.apply`` and ``grid.show`` hand OCCT, read off the scene at the
seam, so both renderers start from the same meshes, placements, materials, camera and lights. It times OCCT's warm
frame for each case.

``compare`` has the core draw every case (``--native``: the core built by tools/native.sh, through its C ABI; else
the Node host on the WebAssembly module, as the engine would ask it), and holds its picture against OCCT's:

  mean     the mean absolute difference per channel, in 8-bit levels
  >8, >32  the share of pixels whose largest channel difference is over 8, over 32 levels
  moved    the share over 32 levels once each picture may shift by a pixel (the difference to the nearest value in
           the other's 3x3 neighbourhood): what is left is not an edge drawn a pixel aside

and writes ``<model>.sheet.<core>.png``, each case a row: OCCT's, the core's, and where they differ. One line per
case with both renderers' times (OCCT's as ``reference`` timed it), then the worst of each measure; ``--json`` writes
the table. It ends 1 where a picture's mean difference is over a level and a half or over 0.5% of it has moved.
``--samples`` is 4 by default: what a software OpenGL gave the reference pictures, of the 8 cad asks for.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import struct
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent.parent

SIZE = (1200, 800)
CASES = [
    # name, display, camera, projection, grid, size
    ("solid", {"mode": "solid"}, "iso", "orthographic", False, SIZE),
    ("shaded", {"mode": "shaded"}, "iso", "orthographic", False, SIZE),
    ("parts", {"mode": "parts"}, "iso", "orthographic", False, SIZE),
    ("xray", {"mode": "xray"}, "iso", "orthographic", False, SIZE),
    ("hidden-line", {"mode": "hidden-line"}, "iso", "orthographic", False, SIZE),
    ("wireframe", {"mode": "wireframe"}, "iso", "orthographic", False, SIZE),
    ("solid-front", {"mode": "solid"}, "front", "orthographic", False, SIZE),
    ("solid-perspective", {"mode": "solid"}, "215:25", "perspective", False, SIZE),
    ("solid-clip", {"mode": "solid", "clip": {"axis": "x"}}, "iso", "orthographic", False, SIZE),
    ("parts-clip", {"mode": "parts", "clip": {"axis": "y", "invert": True}}, "35:30", "perspective", False, SIZE),
    ("solid-grid", {"mode": "solid"}, "iso", "orthographic", True, SIZE),
    ("grid-perspective", {"mode": "shaded"}, "140:20", "perspective", True, SIZE),
    ("solid-tall", {"mode": "solid"}, "iso", "orthographic", False, (640, 900)),
    ("perspective-tall", {"mode": "solid"}, "35:30", "perspective", False, (640, 900)),
]


# --- the scene the core draws from -----------------------------------------------------------------------------


class Payloads:
    """A scene's binary parts, each kept once by its content."""

    def __init__(self, folder: Path | None = None) -> None:
        self.folder = folder
        self.names: list[str] = []
        self.data: dict[str, bytes] = {}

    def add(self, data: bytes) -> int:
        name = hashlib.sha256(data).hexdigest()[:24]
        if name not in self.data:
            self.data[name] = data
            if self.folder is not None and not (self.folder / name).exists():
                (self.folder / name).write_bytes(data)
        if name not in self.names:
            self.names.append(name)
        return self.names.index(name)


def _ranges(mesh, chosen) -> list[list[int]] | None:
    """The index ranges of a mesh's faces whose ordinals ``chosen`` holds, runs joined; None for every face."""
    rows = np.asarray(mesh.faces, np.int64).reshape(-1, 3)
    if chosen is None:
        return None
    found: list[list[int]] = []
    for ordinal, first, count in rows.tolist():
        if ordinal not in chosen or not count:
            continue
        if found and found[-1][0] + found[-1][1] == first:
            found[-1][1] += count
        else:
            found.append([first, count])
    return found


def _groups(prototype) -> dict[int, object]:
    """``shapes.prototype_shapes``: each painted face's group, by ordinal."""
    from cad.engine.render.shapes import FaceGroup

    colors = prototype.get("faceColors") or {}
    materials = prototype.get("faceMaterials") or {}
    groups = {}
    for ordinal in set(colors) | set(materials):
        material = materials.get(ordinal)
        raw = colors.get(ordinal)
        key = None if material is None else json.dumps(material, sort_keys=True, separators=(",", ":"), allow_nan=False)
        groups[int(ordinal)] = FaceGroup(tuple(raw) if raw is not None else None, key)
    return groups


def scene_of(scene, *, grid: bool = False, payloads: Payloads | None = None,
             texels: dict | None = None) -> tuple[dict, Payloads]:
    """What ``scene`` (shown and framed) hands OCCT, as the core's scene: plain numbers and buffers. ``texels``: a
    textured part's texture coordinates, a pair a node of its mesh, by its key (a GLB's, ``read_file``)."""
    from cad.engine.render import clip as section
    from cad.engine.render import finish
    from cad.engine.render.look import LOOK
    from cad.engine.render.occt import (BACKGROUND, EDGE, EDGES_WIN_OFFSET, PARTS, ROBOTS, SEE_THROUGH_OFFSET)
    from cad.engine.render.shapes import _LINE_OF, LINES, FaceGroup

    payloads = payloads or Payloads()
    placements: list[bytes] = []

    def placed(index: int) -> int:
        # An instance's matrix, sixteen doubles column-major, by its place among the scene's.
        data = np.ascontiguousarray(scene.placement(index).T, "<f8").tobytes()
        if data not in placements:
            placements.append(data)
        return placements.index(data)

    display, mode, preview = scene.display, scene.mode, scene.preview
    look = "hidden" if mode == "hidden-line" else "xray" if mode == "xray" else "pbr" if preview else "lit"
    faces = mode != "wireframe"
    edges = not preview and mode != "shaded" and not (mode in ("solid", "parts")
                                                      and scene.structure.get("kind") in ROBOTS)
    classes = (display.get("edges") or {}).get("classes") or LINES
    layer = "topmost" if mode in ("xray", "wireframe") else "default"
    backdrop = list(finish.linear(scene.background or BACKGROUND))
    meshes: list[int] = []
    mesh_of: dict[int, int] = {}
    groups_of: dict[int, dict] = {}
    draw: list[dict] = []
    clip = display.get("clip")
    cut = bool(clip) and clip.get("enabled") is not False

    def mesh_index(p: int) -> int:
        if p not in mesh_of:
            mesh_of[p] = len(meshes)
            meshes.append(payloads.add(scene.meshes[scene.prototypes[p]["key"]].to_bytes()))
        return mesh_of[p]

    for index, instance in enumerate(scene.structure["instances"]):
        if index in scene.hidden:
            continue
        p = instance["prototype"]
        prototype = scene.prototypes[p]
        part = scene.parts[p]
        mesh = scene.meshes[prototype["key"]]
        matrix = placed(index)
        rgba = instance.get("color") or prototype.get("color")
        rgba = tuple(rgba) if rgba else None
        if mode == "parts":
            rgba = PARTS[instance.get("palette", index) % len(PARTS)]
        if faces:
            if p not in groups_of:
                groups_of[p] = _groups(prototype)
            painted = groups_of[p]
            for group in part.faces:
                color = rgba if group is None or mode == "parts" else (
                    (group.color if group.color is not None else rgba) if isinstance(group, FaceGroup) else group)
                if len(part.faces) == 1:
                    ranges = None
                elif group is None:
                    ranges = _ranges(mesh, {int(o) for o in np.asarray(mesh.faces).reshape(-1, 3)[:, 0]} - set(painted))
                else:
                    ranges = _ranges(mesh, {o for o, g in painted.items() if g == group})
                item: dict = {"faces": mesh_index(p), "matrix": matrix, "layer": "default"}
                if ranges is not None:
                    item["ranges"] = ranges
                fill = isinstance(color, str)
                own = None if fill else scene._material_of(p, group)
                if look == "hidden":
                    item.update(shading="unlit", color=backdrop, alpha=1.0)
                elif look == "xray":
                    base = finish.linear(color if color is not None else LOOK.fill)
                    item.update(shading="phong", color=list(base), alpha=LOOK.mode("xray").opacity)
                elif look == "pbr" and own is None:
                    # Preview's surface without a material (Scene._material): its colour as it is, opaque, OCCT's
                    # default PBR material at normalized roughness 0.5.
                    base = finish.linear(color if color is not None else LOOK.fill)
                    item.update(shading="pbr", color=list(base), alpha=1.0, metallic=0.0, roughness=0.01 + 0.99 * 0.5,
                                ior=1.5, emission=[0.0, 0.0, 0.0])
                else:
                    if fill:
                        own_colour = prototype.get("color") or ()
                        color = (*finish.linear(color), float(own_colour[3]) if len(own_colour) > 3 else 1.0)
                    found = finish.finish(color, own)
                    item.update(shading="pbr", color=list(found["color"]), alpha=found["alpha"],
                                metallic=found["metallic"], roughness=found["roughness"], ior=found["ior"],
                                emission=list(found["emission"]))
                texture = part.textures.get(group) if look in ("lit", "pbr") and not fill else None
                if texture is not None and texels and prototype["key"] in texels:
                    # A GLB's base colour texture over its material's colour (Scene._faces, SetTextureSet).
                    picture = texture_picture(texture)
                    item["texels"] = payloads.add(np.ascontiguousarray(texels[prototype["key"]], np.float32).tobytes())
                    item["texture"] = {"payload": payloads.add(picture.tobytes()), "width": picture.shape[1],
                                       "height": picture.shape[0]}
                see_through = look == "xray" or (look != "hidden" and item["alpha"] < 1)
                item["offset"] = list(SEE_THROUGH_OFFSET if see_through else EDGES_WIN_OFFSET)
                draw.append(item)
        if edges:
            for line in LINES:
                if line not in part.edges or line not in classes:
                    continue
                draw.append({"edges": mesh_index(p), "classes": sorted(c for c, n in _LINE_OF.items() if n == line),
                             "matrix": matrix, "color": list(finish.linear(EDGE[line])), "width": LOOK.edge_width,
                             "layer": layer})
    found: dict = {
        "width": scene.canvas.width, "height": scene.canvas.height, "samples": 8, "background": backdrop,
        "camera": camera_of(scene.camera),
    }
    if look == "xray":
        found["phong"] = {"ambient": LOOK.xray.ambient, "specular": LOOK.xray.specular, "shininess": LOOK.xray.shininess,
                          "lights": [{"direction": list(light.direction), "intensity": light.intensity}
                                     for light in LOOK.xray.lights]}
    elif preview:
        found["light"] = preview_light(payloads)
    else:
        radiance = np.ascontiguousarray(finish.environment(), np.float32)
        found["light"] = {
            "lights": [{"direction": list(light.direction), "intensity": light.intensity} for light in LOOK.lights],
            "environment": {"payload": payloads.add(radiance.tobytes()), "width": radiance.shape[1],
                            "height": radiance.shape[0], "intensity": LOOK.environment.intensity}}
    if cut:
        plane = section.plane(scene, clip)
        normal, point = plane.Axis().Direction(), plane.Location()
        n = [normal.X(), normal.Y(), normal.Z()]
        found["clip"] = [*n, -(n[0] * point.X() + n[1] * point.Y() + n[2] * point.Z())]
        if mode != "wireframe":
            for index, instance in enumerate(scene.structure["instances"]):
                p = instance["prototype"]
                if index in scene.hidden or not len(scene.meshes[scene.prototypes[p]["key"]].indices):
                    continue
                draw.append({"cap": mesh_index(p), "matrix": placed(index),
                             "color": list(section.cap_colour(scene, index, clip))})
    if grid:
        from cad.engine.render import grid as paper

        low, high = scene.rest_bounds()
        bands = paper.bands(paper.paper(low, high), paper.Lens(scene.camera, scene.canvas.width, scene.canvas.height))
        if len(bands.triangles):
            texels = paper.profile(LOOK.backdrop)
            picture = (np.clip(texels, 0, 1) * 255.0).astype(np.uint8)  # as OCCT's pixmap takes a colour: cut short
            draw.append({
                "triangles": {"positions": payloads.add(np.ascontiguousarray(bands.points, np.float32).tobytes()),
                              "texels": payloads.add(np.ascontiguousarray(bands.texels, np.float32).tobytes()),
                              "indices": payloads.add(np.ascontiguousarray(bands.triangles, np.uint32).tobytes())},
                "texture": {"payload": payloads.add(picture.tobytes()), "width": picture.shape[1],
                            "height": picture.shape[0]},
                "color": [1.0, 1.0, 1.0, 1.0], "blend": True, "offset": [1.0, 1.0], "clip": False, "layer": "default"})
    found["meshes"] = meshes
    found["matrices"] = payloads.add(b"".join(placements))
    found["draw"] = draw
    return found, payloads


def preview_light(payloads: Payloads) -> dict:
    """``Scene.preview_look``'s rig as the core's light: the key (its direction, its strength, the shadow map it casts
    at 4096 texels with a bias of 0.002) and the environment at full strength, baked as ``STUDIO_BAKE`` asks."""
    from cad.engine.render import finish
    from cad.engine.render.occt import KEY_DIRECTION, KEY_ILLUMINANCE, STUDIO_BAKE

    radiance = np.ascontiguousarray(finish.environment(), np.float32)
    key = -np.asarray(KEY_DIRECTION, float) / np.linalg.norm(KEY_DIRECTION)
    return {"lights": [{"direction": key.tolist(), "intensity": KEY_ILLUMINANCE,
                        "shadow": {"resolution": 4096, "bias": 0.002}}],
            "environment": {"payload": payloads.add(radiance.tobytes()), "width": radiance.shape[1],
                            "height": radiance.shape[0], "intensity": 1.0,
                            "specularSize": STUDIO_BAKE["PbrEnvPow2Size"],
                            "specularSamples": STUDIO_BAKE["PbrEnvBakingSpecNbSamples"]}}


def texture_picture(texture) -> np.ndarray:
    """A texture set's first texture (the base colour's) as RGBA bytes, the top row first: the image OCCT reads."""
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


def read_file(path: Path) -> tuple[dict, dict, list | None, dict]:
    """A file as today's renderer is handed it: its structure, its parts' buffers, the shapes made for parts a buffer
    does not carry whole (None: made from the buffers), and the texture coordinates of the textured parts by key."""
    from cad.engine.mesh import mesh_shape, shape_bytes

    if path.suffix.lower() == ".xbf":
        from cad.engine.document import Loaded

        loaded = Loaded(path)
        buffers = {p.key: mesh_shape(shape_bytes(p.shape, read=True), parallel=False).to_bytes()
                   for p in loaded.prototypes}
        return loaded.structure(), buffers, None, {}
    from cad.engine.formats import read
    from cad.engine.mesh_format import Mesh
    from cad.engine.render.shapes import prototype_shapes

    foreign = read(path)
    prototypes = foreign.structure["prototypes"]
    parts = [foreign.shapes.get(p["key"]) or prototype_shapes(p, Mesh.from_bytes(foreign.buffers[p["key"]]))
             for p in prototypes]
    texels = {}
    if path.suffix.lower() == ".glb":
        from cad.engine.formats.glb import read_glb

        for prototype, part in zip(prototypes, read_glb(path)[0]):
            if part.uvs is not None:
                texels[prototype["key"]] = part.uvs
    return foreign.structure, foreign.buffers, parts, texels


def camera_of(camera: dict) -> dict:
    """``Scene.frame``'s record as the core's camera: where it stands, and its height (the view's, in the
    model's units) or its vertical field of view in degrees."""
    found = {"projection": camera["projection"], "eye": [float(v) for v in camera["eye"]],
             "target": [float(v) for v in camera["target"]], "up": [float(v) for v in camera["up"]]}
    if camera["projection"] == "perspective":
        found["fov"] = float(camera["fov"])
    else:
        found["height"] = float(camera["scale"])
    return found


def project(camera: dict, width: int, height: int, points: np.ndarray) -> np.ndarray:
    """World points to output pixels (x right, y down) through the core's camera: the check of ``camera_of``
    against OCCT's own projection."""
    eye, target = np.array(camera["eye"]), np.array(camera["target"])
    back = (eye - target) / np.linalg.norm(eye - target)
    right = np.cross(camera["up"], back)
    right /= np.linalg.norm(right)
    up = np.cross(back, right)
    v = np.asarray(points, float) - eye
    x, y, depth = v @ right, v @ up, -(v @ back)
    if camera["projection"] == "perspective":
        focal = (height / 2) / math.tan(math.radians(camera["fov"]) / 2)
        return np.column_stack([width / 2 + focal * x / depth, height / 2 - focal * y / depth])
    pixel = camera["height"] / height
    return np.column_stack([width / 2 + x / pixel, height / 2 - y / pixel])


# --- the reference pictures ------------------------------------------------------------------------------------


def variants(path: Path, structure: dict) -> list[tuple[str, dict]]:
    """The file as it is, and for the hinged box one with a see-through part beside it."""
    found = [(path.stem, structure)]
    if path.stem == "hinged_box_showcase":
        glass = json.loads(json.dumps(structure))
        for at, prototype in enumerate(glass["prototypes"]):
            if at % 2 == 0:
                color = list(prototype.get("color") or (0.5, 0.7, 0.9, 1.0))
                prototype["color"] = [*color[:3], 0.35]
        for instance in glass["instances"]:
            instance.pop("color", None)
        found.append((path.stem + "_glass", glass))
    return found


def reference(args: argparse.Namespace) -> int:
    from cad.engine.render.context import encode
    from cad.engine.render.occt import Scene

    out = Path(args.out)
    (out / "payloads").mkdir(parents=True, exist_ok=True)
    payloads = Payloads(out / "payloads")
    for file in args.files:
        path = Path(file)
        structure, buffers, parts, texels = read_file(path)
        for model, shown in variants(path, structure):
            folder = out / model
            folder.mkdir(exist_ok=True)
            scenes: dict[tuple[int, int], Scene] = {}
            rows = []
            for name, display, camera, projection, grid, size in CASES:
                if args.only and name not in args.only:
                    continue
                scene = scenes.get(size)
                if scene is None:
                    scene = scenes[size] = Scene(path, buffers, size=size, structure=shown, parts=parts)
                seconds = {}
                for turn in range(2):  # the second time is the warm one
                    clock = time.perf_counter()
                    scene.show(display)
                    scene.frame(camera, projection)
                    scene.grid(grid)
                    seconds["set"] = time.perf_counter() - clock
                    clock = time.perf_counter()
                    frame = scene.canvas.frame()
                    seconds["frame"] = time.perf_counter() - clock
                clock = time.perf_counter()
                frame = scene.canvas.frame()
                seconds["frame"] = min(seconds["frame"], time.perf_counter() - clock)
                clock = time.perf_counter()
                png = encode(frame)
                seconds["png"] = time.perf_counter() - clock
                (folder / f"{name}.occt.png").write_bytes(png)
                described, _ = scene_of(scene, grid=grid, payloads=payloads, texels=texels)
                corners = scene.box_corners()
                drift = float(np.abs(project(described["camera"], *size, corners) - scene.project(corners)).max())
                described["payloads"] = [len(payloads.data[n]) if n in payloads.data else (out / "payloads" / n).stat().st_size
                                         for n in payloads.names]
                cam = scene.canvas.view.Camera()
                manifest = {"scene": described, "files": list(payloads.names),
                            "occt": {"seconds": {k: round(v, 4) for k, v in seconds.items()},
                                     "near": cam.ZNear(), "far": cam.ZFar(), "camera_drift_px": drift},
                            "case": {"display": display, "camera": camera, "projection": projection, "grid": grid}}
                (folder / f"{name}.json").write_text(json.dumps(manifest))
                rows.append((name, seconds, drift))
                print(f"{model:28} {name:18} set {seconds['set']*1000:7.1f} ms  frame {seconds['frame']*1000:7.1f} ms"
                      f"  png {seconds['png']*1000:6.1f} ms  camera {drift:.4f} px", flush=True)
            for scene in scenes.values():
                scene.canvas.close()
    return 0


# --- Preview ---------------------------------------------------------------------------------------------------


class Staged:
    """A presentation of Preview's studio (``Scene._structure``) kept for the core: its triangles as the scene's
    ``triangles`` draw, shown or put away as the scene puts its structures away."""

    def __init__(self, triangles, aspect: dict, priority) -> None:
        from OCP.collections import Vec4_uint8_t
        from OCP.Graphic3d import Graphic3d_DisplayPriority

        count = triangles.VertexNumber()
        corners = [triangles.Vertice(i) for i in range(1, count + 1)]
        self.positions = np.array([(p.X(), p.Y(), p.Z()) for p in corners], np.float32)
        self.indices = np.array([triangles.Edge(i) - 1 for i in range(1, triangles.EdgeNumber() + 1)], np.uint32)
        self.colors = self.texels = None
        if triangles.HasVertexColors():
            colours = []
            for i in range(1, count + 1):
                colour = Vec4_uint8_t(0, 0, 0, 0)
                triangles.VertexColor(i, colour)
                colours.append((colour.x(), colour.y(), colour.z(), colour.w()))
            self.colors = np.array(colours, np.uint8)
        if triangles.HasVertexTexels():
            self.texels = np.array([(t.X(), t.Y()) for t in (triangles.VertexTexel(i) for i in range(1, count + 1))],
                                   np.float32)
        self.texture = aspect.get("texture")
        self.below = priority == Graphic3d_DisplayPriority.Graphic3d_DisplayPriority_Below
        self.shown = True

    def Erase(self) -> None:
        self.shown = False

    def Remove(self) -> None:
        self.shown = False

    def Display(self) -> None:
        self.shown = True

    def item(self, payloads: Payloads) -> dict:
        """The core's draw of it: unlit, blended, in the default layer, never cut, kept out of the fit."""
        found = {"positions": payloads.add(self.positions.tobytes()), "indices": payloads.add(self.indices.tobytes())}
        item: dict = {"triangles": found, "color": [1.0, 1.0, 1.0, 1.0], "blend": True, "offset": [1.0, 1.0],
                      "clip": False, "infinite": True, "layer": "default"}
        if self.colors is not None:
            found["colors"] = payloads.add(self.colors.tobytes())
        if self.texels is not None:
            found["texels"] = payloads.add(self.texels.tobytes())
        if self.texture is not None:
            picture = _rgba(self.texture["picture"])
            item["texture"] = {"payload": payloads.add(picture.tobytes()), "width": picture.shape[1],
                               "height": picture.shape[0]}
        return item


def _shown(picture: np.ndarray) -> np.ndarray:
    """The view's background picture as OCCT shows it stretched over the frame (``Aspect_FM_STRETCH``): every row of
    the frame reads the texture's first row (v = 0), which is the picture's last (``Scene._texture`` sets a pixmap
    whose rows run up), so it is that row across the frame, the same all the way down."""
    return np.ascontiguousarray(picture[-1:])


def _rgba(picture: np.ndarray) -> np.ndarray:
    if picture.shape[2] == 4:
        return np.ascontiguousarray(picture, np.uint8)
    return np.ascontiguousarray(np.concatenate([picture, np.full(picture.shape[:2] + (1,), 255, np.uint8)], -1))


class CoreCanvas:
    """What cad's Preview code asks of ``Scene.canvas`` (its size, the view's background picture, a frame), the
    frame drawn by the core from the scene as shown: the model (``scene_of``), the studio's presentations still
    shown, the picture behind."""

    def __init__(self, scene, core, width: int, height: int) -> None:
        self.scene, self.core, self.width, self.height = scene, core, width, height
        self.picture = None  # the view's background image: (picture, smooth), stretched over the frame
        self.seconds = 0.0  # the core's time, every frame and depth it was asked for
        self.depths: list[np.ndarray] = []
        canvas = self

        class Graphic:
            def SetBackgroundImage(self, texture, _update=False):
                canvas.picture = texture

            def SetBackgroundImageStyle(self, *_args):
                pass

        class View:
            def View(self):
                return Graphic()

        self.view = View()

    def scene_now(self, payloads: Payloads) -> dict:
        found, _ = scene_of(self.scene, payloads=payloads)
        shown = [staged for staged in self.scene.stage if staged.shown]
        # OCCT draws a layer's structures by display priority: the floor (Below) before the model, the shadow after.
        found["draw"] = ([s.item(payloads) for s in shown if s.below] + found["draw"]
                         + [s.item(payloads) for s in shown if not s.below])
        if self.picture is not None:
            picture = _shown(np.asarray(self.picture["picture"][..., :3], np.uint8))
            found["backdrop"] = {"payload": payloads.add(picture.tobytes()), "width": picture.shape[1],
                                 "height": picture.shape[0]}
        return found

    def draw(self, found: dict, payloads: Payloads) -> bytes:
        found["payloads"] = [len(payloads.data[name]) for name in payloads.names]
        data, seconds = self.core.render(found, b"".join(payloads.data[name] for name in payloads.names))
        self.seconds += seconds
        return data

    def frame(self) -> np.ndarray:
        payloads = Payloads()
        found = self.scene_now(payloads)
        found["samples"] = 4
        data = self.draw(found, payloads)
        return np.frombuffer(data, np.uint8).reshape(self.height, self.width, 4)[..., :3].copy()

    def depth(self, eye, target, up, scale: float, size: int, z_range=None, keep_above: float | None = None):
        """``Scene._depth`` by the core: the model's depth from an orthographic camera, one sample a pixel, then
        through the 8-bit picture OCCT dumps a depth into (stretched over its own range, FreeImage's rounding)
        and back, as ``_depth`` reads it."""
        # OCCT draws the square picture with the view's own aspect: the scale spans the picture's height (its width
        # where the view is taller than wide) and the other side spans the scale times the aspect, squeezed into
        # the square. The core's pixels are square, so the model is squeezed instead, along that side of the
        # camera (no depth, and no height above the floor, changes).
        aspect = self.width / self.height
        back = np.asarray(eye, float) - np.asarray(target, float)
        back /= np.linalg.norm(back)
        right = np.cross(np.asarray(up, float), back)
        right /= np.linalg.norm(right)
        axis, squeeze = (right, 1 / aspect) if aspect >= 1 else (np.cross(back, right), aspect)
        squeezed = np.eye(4)
        squeezed[:3, :3] += (squeeze - 1) * np.outer(axis, axis)
        squeezed[:3, 3] = (np.eye(3) - squeezed[:3, :3]) @ np.asarray(target, float)
        placement = self.scene.placement
        self.scene.placement = lambda index: squeezed @ placement(index)
        try:
            payloads = Payloads()
            found, _ = scene_of(self.scene, payloads=payloads)
        finally:
            del self.scene.placement
        camera = {"projection": "orthographic", "eye": [float(v) for v in eye], "target": [float(v) for v in target],
                  "up": [float(v) for v in up], "height": float(scale)}
        if z_range is not None:
            camera["near"], camera["far"] = float(z_range[0]), float(z_range[1])
        found.update(width=size, height=size, samples=1, format="depth", camera=camera)
        if keep_above is not None:  # z >= keep_above, where the model was squeezed
            normal = np.linalg.solve(squeezed[:3, :3].T, [0.0, 0.0, 1.0])
            point = squeezed[:3, :3] @ [0.0, 0.0, float(keep_above)] + squeezed[:3, 3]
            found["clip"] = [*normal.tolist(), -float(normal @ point)]
            for item in found["draw"]:
                item.pop("clip", None)
        depth = np.frombuffer(self.draw(found, payloads), np.float32).reshape(size, size)
        self.depths.append(occt_depth_dump(depth))
        return self.depths[-1]


def occt_depth_dump(depth: np.ndarray) -> np.ndarray:
    """A depth picture as ``Scene._depth`` reads OCCT's back: FreeImage's float-to-byte picture (stretched from its
    least to its most, ``(BYTE)(scale * (value - least) + 0.5)``), then the two ends read as floats where the
    bytes are least and most, and the bytes put back between them."""
    least, most = float(depth.min()), float(depth.max())
    if most == least:
        least, most = 0.0, 255.0
    scale = 255.0 / (most - least)
    levels = np.floor(scale * (depth - np.float32(least)).astype(np.float64) + 0.5).astype(np.uint8).astype(np.float64)
    low_at, high_at = np.unravel_index(levels.argmin(), levels.shape), np.unravel_index(levels.argmax(), levels.shape)
    low, high = float(depth[low_at]), float(depth[high_at])
    return low + levels / 255.0 * (high - low)


def preview_core(scene, core) -> tuple[np.ndarray, dict]:
    """Preview drawn by the core, by cad's own Preview code (``Scene._studio``, ``_studio_backdrop``, ``painter``)
    with the scene's OCCT calls swapped for the core's: its canvas, ``_depth`` and ``_structure``. ``scene`` is
    shown with ``preview=True`` and framed. The picture, and the seconds the core took and all took."""
    started = time.perf_counter()
    canvas = CoreCanvas(scene, core, scene.canvas.width, scene.canvas.height)
    scene.stage = []
    scene.canvas = canvas
    scene._depth = canvas.depth
    scene._structure = lambda triangles, aspect, priority: scene.stage.append(Staged(triangles, aspect, priority))
    scene._unlit = lambda texture=None: {"texture": texture}
    scene._texture = lambda picture, smooth=True: {"picture": np.asarray(picture), "smooth": smooth}
    scene.clear_stage = lambda: scene.stage.clear()
    scene._studio()
    scene._studio_backdrop()
    scene.studio, scene.traced = True, False
    studio = time.perf_counter() - started
    frame = canvas.frame()
    paint = scene.painter()
    if paint is not None:
        paint(frame)
    return frame, {"core": canvas.seconds, "studio": studio, "all": time.perf_counter() - started,
                   "depths": canvas.depths}


def preview(args: argparse.Namespace) -> int:
    """Today's Preview and the core's of each file, side by side: ``<model>/preview.occt.png``, ``.<core>.png``."""
    from cad.engine.render.occt import Scene
    from PIL import Image

    out = Path(args.out)
    core = Native(args.native) if args.native else Node(args.node, Path(args.wasm))
    table = []
    for file in args.files:
        path = Path(file)
        structure, buffers, parts, _texels = read_file(path)
        for model, shown in variants(path, structure):
            folder = out / model
            folder.mkdir(parents=True, exist_ok=True)
            scene = Scene(path, buffers, size=SIZE, structure=shown, parts=parts)
            scene.show({}, preview=True)
            scene.frame(args.camera, "perspective")
            depths: list[np.ndarray] = []  # today's two depth pictures, to hold the core's against
            occt_depth = scene._depth
            scene._depth = lambda *a, kept=depths, drawn=occt_depth, **k: kept.append(drawn(*a, **k)) or kept[-1]
            clock = time.perf_counter()
            scene.preview_look(0)
            look = time.perf_counter() - clock
            scene._depth = occt_depth
            today = {}
            for turn in range(2):  # the second time is the warm one
                clock = time.perf_counter()
                want = scene.canvas.frame()
                paint = scene.painter()
                if paint is not None:
                    paint(want)
                today["frame"] = time.perf_counter() - clock
            Image.fromarray(want).save(folder / "preview.occt.png")
            occt_canvas = scene.canvas
            for turn in range(args.times):
                got, seconds = preview_core(scene, core)
            for name, ours, theirs in zip(("contact", "key"), seconds["depths"], depths):
                print(f"{model:28} depth {name:8} largest difference {np.abs(ours - theirs).max():.6f}, "
                      f"over 1/255: {(np.abs(ours - theirs) > 1 / 255).mean() * 100:.3f}%", flush=True)
            Image.fromarray(got).save(folder / f"preview.{core.name}.png")
            numbers = measure(want, got)
            print(f"{model:28} preview  mean {numbers['mean']!s:22} >8 {numbers['over8']:6.2f}%  >32 "
                  f"{numbers['over32']:6.2f}%  moved>32 {numbers['moved32']:6.2f}%  OpenGL look {look*1000:6.0f} ms "
                  f"frame {today['frame']*1000:6.1f} ms  {core.name} {seconds['core']*1000:6.1f} ms "
                  f"(studio {seconds['studio']*1000:5.0f} ms, all {seconds['all']*1000:5.0f} ms)", flush=True)
            table.append({"model": model, "case": "preview", **numbers, "occt_ms": round(today["frame"] * 1000, 1),
                          "core_ms": round(seconds["core"] * 1000, 1)})
            sheet([("preview", want, got, numbers)], out / f"{model}.preview.{core.name}.png")
            occt_canvas.close()
    core.close()
    if args.json:
        Path(args.json).write_text(json.dumps(table, indent=1))
    worst_mean = max(max(row["mean"]) for row in table)
    worst_moved = max(row["moved32"] for row in table)
    print(f"{len(table)} pictures: the largest mean difference {worst_mean:.3f} levels, the largest share moved over 32 "
          f"levels {worst_moved:.3f}%")
    return 0 if worst_mean <= 1.5 and worst_moved <= 0.5 else 1


# --- the core's pictures ---------------------------------------------------------------------------------------


class Native:
    """The core built natively, through its C ABI."""

    name = "native"

    def __init__(self, library: str) -> None:
        self.lib = ctypes.CDLL(library)
        self.lib.vc_render.restype = ctypes.c_void_p
        self.lib.vc_render.argtypes = [ctypes.c_char_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32,
                                       ctypes.POINTER(ctypes.c_uint32)]
        self.lib.vc_free.argtypes = [ctypes.c_void_p]
        self.lib.vc_last_error.restype = ctypes.c_char_p

    def render(self, scene: dict, blob: bytes) -> tuple[bytes, float]:
        text = json.dumps(scene, separators=(",", ":")).encode()
        size = ctypes.c_uint32()
        clock = time.perf_counter()
        pointer = self.lib.vc_render(text, len(text), blob, len(blob), ctypes.byref(size))
        seconds = time.perf_counter() - clock
        if not pointer:
            raise RuntimeError(self.lib.vc_last_error().decode())
        data = ctypes.string_at(pointer, size.value)
        self.lib.vc_free(pointer)
        return data, seconds

    def close(self) -> None:
        pass


class Node:
    """hosts/node/serve.mjs on the WebAssembly module: a ``render`` job a frame out and a frame back."""

    name = "wasm"

    def __init__(self, node: str, wasm: Path, kept: bool = False) -> None:
        self.process = subprocess.Popen([node, str(HERE / "hosts/node/serve.mjs"), str(wasm)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE)
        self.ids = 0
        self.kept = kept  # buffers are sent once, under their keys, and named after
        self.sent: set[str] = set()
        self.wire = 0  # bytes written to the host by the last job
        self.round_trip = 0.0  # and the seconds from asking to the answer read

    def job(self, name: str, payloads: tuple = (), **header) -> tuple[dict, list[bytes]]:
        self.ids += 1
        head = json.dumps({"id": self.ids, "job": name, **header, "payloads": [len(p) for p in payloads]}).encode()
        body = struct.pack(">I", len(head)) + head + b"".join(payloads)
        clock = time.perf_counter()
        self.process.stdin.write(struct.pack(">Q", len(body)) + body)
        self.process.stdin.flush()
        self.wire = 8 + len(body)
        (length,) = struct.unpack(">Q", self._read(8))
        answer = self._read(length)
        (head_length,) = struct.unpack(">I", answer[:4])
        self.round_trip = time.perf_counter() - clock
        found = json.loads(answer[4:4 + head_length])
        if not found.get("ok"):
            raise RuntimeError(f"{name}: {found.get('error')}")
        parts, at = [], 4 + head_length
        for size in found["payloads"]:
            parts.append(answer[at:at + size])
            at += size
        return found, parts

    def _read(self, count: int) -> bytes:
        data = self.process.stdout.read(count)
        if len(data) < count:
            raise EOFError("the host ended")
        return data

    def render(self, scene: dict, blob: bytes) -> tuple[bytes, float]:
        parts, at = [], 0
        for length in scene.get("payloads") or []:
            parts.append(blob[at:at + length])
            at += length
        plain = {k: v for k, v in scene.items() if k != "payloads"}
        if not self.kept:
            found, answer = self.job("render", tuple(parts), scene=plain)
            return answer[0], found["seconds"]
        keys = [hashlib.sha256(part).hexdigest()[:24] for part in parts]
        for _ in range(2):  # a second time with what the host says it lacks
            found, answer = self.job("render", tuple(b"" if key in self.sent else part for key, part in zip(keys, parts)),
                                     scene=plain, keys=keys)
            self.sent.update(keys)
            if "missing" not in found:
                return answer[0], found["seconds"]
            self.sent.difference_update(found["missing"])
        raise RuntimeError("the host keeps no buffer it is sent")

    def memory(self) -> int:
        return self.job("about")[0]["memoryBytes"]

    def close(self) -> None:
        self.job("close")
        self.process.stdin.close()
        self.process.wait(30)


def load_case(folder: Path, name: str, root: Path) -> tuple[dict, bytes, dict]:
    manifest = json.loads((folder / f"{name}.json").read_text())
    blob = b"".join((root / "payloads" / file).read_bytes() for file in manifest["files"])
    return manifest["scene"], blob, manifest


def read_png(path: Path) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB"))


def spread(picture: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Each pixel's lowest and highest value per channel over its 3x3 neighbourhood."""
    padded = np.pad(picture, ((1, 1), (1, 1), (0, 0)), mode="edge")
    views = [padded[y:y + picture.shape[0], x:x + picture.shape[1]] for y in range(3) for x in range(3)]
    stack = np.stack(views)
    return stack.min(0), stack.max(0)


def measure(want: np.ndarray, got: np.ndarray) -> dict:
    a, b = want.astype(np.int16), got.astype(np.int16)
    difference = np.abs(a - b)
    worst = difference.max(-1)
    low_a, high_a = spread(a)
    low_b, high_b = spread(b)
    # How far each pixel is from the nearest value its neighbourhood in the other picture holds, both ways.
    aside = np.maximum(np.maximum(low_b - a, a - high_b), np.maximum(low_a - b, b - high_a)).clip(min=0).max(-1)
    return {"mean": [round(float(v), 3) for v in difference.reshape(-1, 3).mean(0)],
            "over8": round(float((worst > 8).mean()) * 100, 3), "over32": round(float((worst > 32).mean()) * 100, 3),
            "moved8": round(float((aside > 8).mean()) * 100, 3), "moved32": round(float((aside > 32).mean()) * 100, 3)}


def sheet(rows: list[tuple[str, np.ndarray, np.ndarray, dict]], path: Path) -> None:
    from PIL import Image, ImageDraw

    cell_w = 600
    strips = []
    for name, want, got, numbers in rows:
        scale = cell_w / want.shape[1]
        size = (cell_w, round(want.shape[0] * scale))
        difference = np.abs(want.astype(np.int16) - got.astype(np.int16)).max(-1)
        heat = np.full(want.shape, 255, np.uint8)
        heat[..., 1] = heat[..., 2] = 255 - np.clip(difference * 4, 0, 255).astype(np.uint8)
        strip = Image.new("RGB", (cell_w * 3 + 16, size[1] + 22), "white")
        for at, picture in enumerate((want, got, heat)):
            strip.paste(Image.fromarray(picture).resize(size, Image.LANCZOS), (at * (cell_w + 8), 22))
        ImageDraw.Draw(strip).text((4, 4), f"{name}: OpenGL | core | difference x4   mean {numbers['mean']}  "
                                           f">8 {numbers['over8']}%  >32 {numbers['over32']}%  moved>32 "
                                           f"{numbers['moved32']}%", fill="black")
        strips.append(strip)
    if not strips:
        return
    total = Image.new("RGB", (max(s.width for s in strips), sum(s.height for s in strips)), "white")
    at = 0
    for strip in strips:
        total.paste(strip, (0, at))
        at += strip.height
    total.save(path)


def compare(args: argparse.Namespace) -> int:
    from PIL import Image

    root = Path(args.out)
    core = Native(args.native) if args.native else Node(args.node, Path(args.wasm), kept=args.kept)
    table = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "payloads"):
        if args.models and folder.name not in args.models:
            continue
        rows = []
        for name, *_ in CASES:
            if not (folder / f"{name}.json").exists() or (args.only and name not in args.only):
                continue
            scene, blob, manifest = load_case(folder, name, root)
            scene["samples"] = args.samples
            best = None
            for _ in range(args.times):
                data, seconds = core.render(scene, blob)
                best = seconds if best is None else min(best, seconds)
            width, height = scene["width"], scene["height"]
            got = np.frombuffer(data, np.uint8).reshape(height, width, 4)[..., :3]
            Image.fromarray(got).save(folder / f"{name}.{core.name}.png")
            want = read_png(folder / f"{name}.occt.png")
            numbers = measure(want, got)
            occt = manifest["occt"]["seconds"]
            table.append({"model": folder.name, "case": name, **numbers, "occt_ms": round(occt["frame"] * 1000, 1),
                          "core_ms": round(best * 1000, 1)})
            rows.append((name, want, got, numbers))
            print(f"{folder.name:28} {name:18} mean {str(numbers['mean']):22} >8 {numbers['over8']:6.2f}%  >32 "
                  f"{numbers['over32']:6.2f}%  moved>8 {numbers['moved8']:6.2f}%  moved>32 {numbers['moved32']:6.2f}%  "
                  f"OpenGL {occt['frame']*1000:7.1f} ms  {core.name} {best*1000:7.1f} ms", flush=True)
        sheet(rows, root / f"{folder.name}.sheet.{core.name}.png")
    if isinstance(core, Node):
        print(f"the host's memory: {core.memory() / 2**20:.0f} MiB")
    core.close()
    if args.json:
        Path(args.json).write_text(json.dumps(table, indent=1))
    if not table:
        print("no case was drawn")
        return 1
    worst_mean = max(max(row["mean"]) for row in table)
    worst_moved = max(row["moved32"] for row in table)
    print(f"{len(table)} pictures: the largest mean difference {worst_mean:.3f} levels, the largest share moved over 32 "
          f"levels {worst_moved:.3f}%")
    # Past these the two are no longer one picture: a level and a half all over, or a pixel in two hundred elsewhere.
    return 0 if worst_mean <= 1.5 and worst_moved <= 0.5 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    made = commands.add_parser("reference")
    made.add_argument("--out", required=True)
    made.add_argument("--only", action="append")
    made.add_argument("files", nargs="+")
    held = commands.add_parser("compare")
    held.add_argument("--out", required=True)
    held.add_argument("--native")
    held.add_argument("--node", default="node")
    held.add_argument("--wasm", default=str(HERE / "dist/viewcore.wasm"))
    held.add_argument("--only", action="append")
    held.add_argument("--models", action="append")
    held.add_argument("--kept", action="store_true",
                      help="send each buffer to the Node host once, under a key, and name it after (render's keys)")
    held.add_argument("--times", type=int, default=2)
    held.add_argument("--samples", type=int, default=4,
                      help="samples a pixel: 4 is what a software OpenGL gave the reference pictures, of the 8 asked")
    held.add_argument("--json")
    studio = commands.add_parser("preview")
    studio.add_argument("--out", required=True)
    studio.add_argument("--native")
    studio.add_argument("--node", default="node")
    studio.add_argument("--wasm", default=str(HERE / "dist/viewcore.wasm"))
    studio.add_argument("--camera", default="iso")
    studio.add_argument("--times", type=int, default=2)
    studio.add_argument("--json")
    studio.add_argument("files", nargs="+")
    args = parser.parse_args(argv)
    return {"reference": reference, "compare": compare, "preview": preview}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
