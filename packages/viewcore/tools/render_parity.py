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

and writes ``<model>.sheet.png``, each case a row: OCCT's, the core's, and where they differ. One line per case with
both renderers' times, then the totals; ``--json`` writes the table.
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


def scene_of(scene, *, grid: bool = False, payloads: Payloads | None = None) -> tuple[dict, Payloads]:
    """What ``scene`` (shown and framed) hands OCCT, as the core's scene: plain numbers and buffers."""
    from cad.engine.render import clip as section
    from cad.engine.render import finish
    from cad.engine.render.look import LOOK
    from cad.engine.render.occt import (BACKGROUND, EDGE, EDGES_WIN_OFFSET, PARTS, ROBOTS, SEE_THROUGH_OFFSET)
    from cad.engine.render.shapes import _LINE_OF, LINES, FaceGroup

    payloads = payloads or Payloads()
    display, mode, preview = scene.display, scene.mode, scene.preview
    if preview:
        raise ValueError("Preview's studio is not the core's to draw")
    look = "hidden" if mode == "hidden-line" else "xray" if mode == "xray" else "lit"
    faces = mode != "wireframe"
    edges = mode != "shaded" and not (mode in ("solid", "parts") and scene.structure.get("kind") in ROBOTS)
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
        matrix = [float(v) for v in scene.placement(index).T.reshape(-1)]
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
                else:
                    if fill:
                        own_colour = prototype.get("color") or ()
                        color = (*finish.linear(color), float(own_colour[3]) if len(own_colour) > 3 else 1.0)
                    found = finish.finish(color, own)
                    item.update(shading="pbr", color=list(found["color"]), alpha=found["alpha"],
                                metallic=found["metallic"], roughness=found["roughness"], ior=found["ior"],
                                emission=list(found["emission"]))
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
                draw.append({"cap": mesh_index(p), "matrix": [float(v) for v in scene.placement(index).T.reshape(-1)],
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
    found["draw"] = draw
    return found, payloads


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
    from cad.engine.document import Loaded
    from cad.engine.mesh import mesh_shape, shape_bytes
    from cad.engine.render.context import encode
    from cad.engine.render.occt import Scene

    out = Path(args.out)
    (out / "payloads").mkdir(parents=True, exist_ok=True)
    payloads = Payloads(out / "payloads")
    for file in args.files:
        path = Path(file)
        loaded = Loaded(path)
        structure = loaded.structure()
        buffers = {p.key: mesh_shape(shape_bytes(p.shape, read=True), parallel=False).to_bytes()
                   for p in loaded.prototypes}
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
                    scene = scenes[size] = Scene(path, buffers, size=size, structure=shown)
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
                described, _ = scene_of(scene, grid=grid, payloads=payloads)
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


# --- the core's pictures ---------------------------------------------------------------------------------------


class Native:
    """The core built natively, through its C ABI."""

    name = "native"

    def __init__(self, library: str) -> None:
        self.lib = ctypes.CDLL(library)
        self.lib.vc_render.restype = ctypes.c_void_p
        self.lib.vc_render.argtypes = [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_size_t,
                                       ctypes.POINTER(ctypes.c_size_t)]
        self.lib.vc_free.argtypes = [ctypes.c_void_p]
        self.lib.vc_last_error.restype = ctypes.c_char_p

    def render(self, scene: dict, blob: bytes) -> tuple[bytes, float]:
        text = json.dumps(scene, separators=(",", ":")).encode()
        size = ctypes.c_size_t()
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

    def __init__(self, node: str, wasm: Path) -> None:
        self.process = subprocess.Popen([node, str(HERE / "hosts/node/serve.mjs"), str(wasm)], stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE)
        self.ids = 0

    def job(self, name: str, payloads: tuple = (), **header) -> tuple[dict, list[bytes]]:
        self.ids += 1
        head = json.dumps({"id": self.ids, "job": name, **header, "payloads": [len(p) for p in payloads]}).encode()
        body = struct.pack(">I", len(head)) + head + b"".join(payloads)
        self.process.stdin.write(struct.pack(">Q", len(body)) + body)
        self.process.stdin.flush()
        (length,) = struct.unpack(">Q", self._read(8))
        answer = self._read(length)
        (head_length,) = struct.unpack(">I", answer[:4])
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
        scene = {k: v for k, v in scene.items() if k != "payloads"}
        found, parts = self.job("render", (blob,), scene=scene, blobs=scene_lengths(blob, scene))
        return parts[0], found["seconds"]

    def memory(self) -> int:
        return self.job("about")[0]["memoryBytes"]

    def close(self) -> None:
        self.job("close")
        self.process.stdin.close()
        self.process.wait(30)


def scene_lengths(blob: bytes, scene: dict) -> list[int]:
    return scene.get("payloads") or []


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
    core = Native(args.native) if args.native else Node(args.node, Path(args.wasm))
    table = []
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and p.name != "payloads"):
        if args.models and folder.name not in args.models:
            continue
        rows = []
        for name, *_ in CASES:
            if not (folder / f"{name}.json").exists() or (args.only and name not in args.only):
                continue
            scene, blob, manifest = load_case(folder, name, root)
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
    return 0


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
    held.add_argument("--times", type=int, default=2)
    held.add_argument("--json")
    args = parser.parse_args(argv)
    return reference(args) if args.command == "reference" else compare(args)


if __name__ == "__main__":
    sys.exit(main())
