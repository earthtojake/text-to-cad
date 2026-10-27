"""The stills' renderer: an engine document drawn by OCCT (``occt.Scene``) from the engine's own
meshes, warm in a process of its own for each document the daemon serves.

**What a renderer holds** (``Held``): one document -- its structure as the engine serves it, each
part's mesh (the XBM buffer the daemon's one mesh cache holds: nothing is meshed again), each
prototype's OCCT shapes (``occt.prototype_shapes``) by its geometry key and paints, and the scenes
drawn from them: one for the display modes and one for Preview (Preview changes the view's lights
and shading for good), each on a canvas of its own, made on first use. A version of the document
(``hold``) keeps the shapes of every part it shares with the last and makes only the new ones; the
scene of the modes is made again from them at once, its presentations computed for the display it
last showed (Preview's on its next picture). A picture (``draw``) is a ``snapshot.Still``: the pose
(the engine's forward kinematics, the scene's instances moved), Explode (``explode.py``), the mode
and clip (``Scene.show``), the camera (a preset, ``az:el`` or -- exactly, for ``--camera authored``
-- a view's own camera by ``Scene.frame``; any other camera object fitted as the snapshot page fits
one, ``frame_camera``), the grid, the annotation and the measurements painted as the page paints
them (``Scene.painter``), and Preview's look; answered as PNG bytes and a report. A scene is let go
of only between pictures, at once and whole (``Held.close``: its canvas closed, then collected):
one collected while another draws took that one's environment map with it.

**The render process** (``python -m cadgen.engine.render.service``): the daemon starts one for a
served document on its first snapshot (``Renders``). It talks as a worker does, frames on its
stdin and its original stdout -- a JSON line and, when it says ``bytes``, that many bytes after
it: ``{"op": "hold", "path", "structure", "meshes": [[key, size]], "bytes"}`` (the structure, then
the buffers of the parts it lacks) answered ``{"held": {...}}``; ``{"op": "frame", "still"}``
answered ``{"done": report, "bytes"}`` and the PNG, ``{"refused": why}`` (a request the document
does not offer, before anything is drawn) or ``{"failed": why}``. A picture of a version the
process does not hold -- a model built again, a file rewritten -- sends it that version first, with
the buffers of the parts it lacks (``_sync``): its other parts' shapes are kept. No timer stops it: it goes
with the daemon, under the workers' memory cap (``CADGEN_ENGINE_WORKER_RSS_MB``, ``worker.rss_cap_mb``),
which counts its memory with theirs and retires an idle one, least recently drawn first, before any
worker (``daemon.Pool.shed``, ``Renders.retire``), and after a frame that leaves it alone over that
cap, when it says so (``retired``) and exits; the next snapshot starts another. A render process is
no worker: it does not count toward the workers' count cap.

**In process** (``draw_here``): ``daemon=False`` and a model drawn from its worker's memory serve
the document from a server of this process, and draw it once.

**A file that is not a document** -- a mesh file, a robot, a DXF (``formats/``) -- is read by its
reader in the process that draws it, into a structure and part buffers as a document's are (a
DXF: a drawing, ``drawing.py``): a render process of its own per file in the daemon
(``{"op": "open", "path"}`` answered ``{"opened": {...}}``, again whenever a file it read has
changed: ``formats.stale``), or once in this process (``draw_here``).

Nothing is written: the verb writes the one PNG it is given.
"""

from __future__ import annotations

import base64
import gc
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable

import numpy as np

__all__ = ["Held", "Renders", "draw_here", "draw_here_each", "frame_camera", "holder", "main", "matte", "picture"]


def _matrix(values: list[float]) -> np.ndarray:
    return np.array(values, float).reshape(4, 4).T  # column-major, as the structure holds it


def _paints(prototype: dict[str, Any]) -> str:
    return json.dumps(prototype.get("faceColors") or {}, sort_keys=True)


# --- the camera --------------------------------------------------------------------------------


def frame_camera(scene: Any, spec: dict[str, Any], projection: str, focal_length: float,
                 padding: float = 0.04, tight: bool = True) -> dict[str, Any]:
    """A camera object (the snapshot contract's: ``position``, ``target``, ``up``, ``direction``,
    ``preset``, ``orthographicHalfHeight``, ``zoom``) on ``scene``'s view, fitted as the snapshot
    page fits one with its tight frame on (``fitOrthographicCamera`` then
    ``applyTightOrthographicFrame``, ``fitPerspectiveCamera``): its direction, up and target, then
    the frame on every placed vertex, ``padding`` of the picture each side; ``tight`` off, on the
    drawn parts' box. Its lengths (``position``, ``target``, ``orthographicHalfHeight``) are in the
    viewer's scene coordinates, as a Quick Edit packet's view carries them
    (``camera_in_millimetres``). (A view's own camera drawn exactly -- ``--camera authored``, a
    job's view with its tight frame off -- is ``Scene.frame``'s.) Sets ``scene.camera`` as
    ``Scene.frame`` does, for the overlays."""
    from OCP.Graphic3d import Graphic3d_Camera
    from OCP.gp import gp_Dir, gp_Pnt

    from cadgen.engine.render.occt import PRESETS, camera_in_millimetres, occt_fov, occt_scale, vertical_fov

    spec = camera_in_millimetres(spec, scene.millimetres_per_scene_unit)

    def vector(name: str) -> np.ndarray | None:
        value = spec.get(name)
        return None if value is None else np.array(value, float)

    preset = PRESETS.get(str(spec.get("preset") or "iso").lower(), PRESETS["iso"])
    position, target = vector("position"), vector("target")
    points = scene.placed_points() if tight else scene.box_corners()
    low, high = points.min(0), points.max(0)
    centre = (low + high) / 2
    radius = max(float(np.linalg.norm(high - low)) / 2, 1.0)
    if target is None:
        target = centre
    if position is not None:
        d = position - target
    else:
        d = vector("direction") if spec.get("direction") is not None else np.array(preset[0], float)
    if not np.linalg.norm(d) > 1e-12:
        raise ValueError("camera.position must differ from camera.target")
    d = d / np.linalg.norm(d)
    up = vector("up") if spec.get("up") is not None else np.array(preset[1], float)
    zoom = float(spec.get("zoom") or 1.0)
    width, height = scene.canvas.width, scene.canvas.height
    aspect = width / height
    forward = -d
    right = np.cross(forward, up)
    if not np.linalg.norm(right) > 1e-12:
        raise ValueError("camera.up must not lie along the direction the camera looks")
    right /= np.linalg.norm(right)
    screen_up = np.cross(right, forward)
    camera = scene.canvas.view.Camera()
    camera.SetAspect(aspect)  # the picture's, so what projects through this camera lands where it is drawn
    fov = vertical_fov(aspect, focal_length)
    if projection == "perspective":
        camera.SetProjectionType(Graphic3d_Camera.Projection_e.Projection_Perspective)
        # three's zoom narrows the field of view.
        fov = float(np.degrees(2 * np.arctan(np.tan(np.radians(fov / 2)) / zoom)))
        camera.SetFOVy(occt_fov(fov, aspect))  # OCCT's spans the width when taller than wide
        if position is not None:
            eye = position
        else:
            safe = max(1 - 2 * padding, 0.1)
            vertical = np.tan(np.radians(fov / 2)) * safe
            horizontal = vertical * aspect
            relative = points - target
            depth = relative @ d
            near = max(radius / 1200, 0.01) * 2
            distance = float(max(np.max(depth + np.abs(relative @ right) / horizontal),
                                 np.max(depth + np.abs(relative @ screen_up) / vertical), np.max(depth + near)))
            eye = target + d * distance
        scale = None
    else:
        camera.SetProjectionType(Graphic3d_Camera.Projection_e.Projection_Orthographic)
        safe = max(1 - 2 * padding, 0.1)
        xs, ys = points @ right, points @ screen_up
        half = max((ys.max() - ys.min()) / (2 * safe), (xs.max() - xs.min()) / (2 * aspect * safe), 1e-6) / zoom
        if spec.get("orthographicHalfHeight"):
            half /= zoom  # the page's camera keeps a given half height's zoom over the frame it fits
        middle = right * (xs.max() + xs.min()) / 2 + screen_up * (ys.max() + ys.min()) / 2
        target = middle + d * float(target @ d)
        eye = target + d * radius * 4
        scale = 2 * half
        camera.SetScale(occt_scale(scale, aspect))
    camera.SetEyeAndCenter(gp_Pnt(*map(float, eye)), gp_Pnt(*map(float, target)))
    camera.SetUp(gp_Dir(*map(float, screen_up)))
    scene.canvas.view.ZFitAll(1.0)
    scene.camera = {"fov": fov, "direction": d, "up": screen_up, "right": right, "eye": eye, "target": target,
                    "projection": projection, "scale": scale}
    if scene.studio:
        scene._studio_backdrop()  # Preview's sweep is shaded for the camera
    return scene.camera


# --- the picture -------------------------------------------------------------------------------


def _linear(srgb: np.ndarray) -> np.ndarray:
    return np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)


def _srgb(linear: np.ndarray) -> np.ndarray:
    return np.where(linear <= 0.0031308, linear * 12.92, 1.055 * np.power(linear, 1 / 2.4) - 0.055)


def matte(canvas: Any, paint: Callable[[np.ndarray], None] | None,
          backdrop: Callable[[Any], None]) -> np.ndarray:
    """The view drawn on nothing (a job's ``output.transparent``), as RGBA bytes: OCCT's backdrop is a
    fill it draws whole, so the view is drawn twice -- on black, then on white (``backdrop`` sets one,
    and None its own again), each painted -- and each pixel's coverage read from the two in linear
    light (where OCCT blends), its colour the black frame's over that coverage."""
    frames = []
    try:
        for colour in ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)):
            backdrop(colour)
            frame = canvas.frame()
            if paint is not None:
                paint(frame)
            frames.append(_linear(frame.astype(np.float64) / 255.0))
    finally:
        backdrop(None)
    black, white = frames
    alpha = np.clip(1.0 - (white - black).mean(-1), 0.0, 1.0)
    colour = np.clip(black / np.maximum(alpha, 1e-6)[..., None], 0.0, 1.0)
    return np.rint(np.concatenate([_srgb(colour), alpha[..., None]], -1) * 255).astype(np.uint8)


def finished(still: Any) -> dict[str, Any]:
    """How a picture was finished, for its report: on nothing, supersampled; nothing when neither."""
    return {**({"transparent": True} if still.transparent else {}),
            **({"renderScale": still.scale} if still.scale != 1 else {})}


def picture(canvas: Any, paint: Callable[[np.ndarray], None] | None, still: Any,
            backdrop: Callable[[Any], None]) -> bytes:
    """The view drawn as a still asks it, as PNG bytes: painted over (``paint``), on nothing when
    it is ``transparent`` (``matte``), and -- drawn ``scale`` times its size, supersampled -- brought
    down to its size, each pixel the mean of those it covers. What the engine draws in pixels (ink,
    text, Measure, the grid) is drawn as heavy against the picture at any scale; OCCT's GL lines
    (edges, a drawing's hairlines) stay one pixel of the larger frame, so they come out finer: a
    core-profile context draws no line wider than a pixel."""
    from PIL import Image

    from cadgen.engine.render.context import encode

    if still.transparent:
        frame = matte(canvas, paint, backdrop)
    else:
        frame = canvas.frame()
        if paint is not None:
            paint(frame)
    width, height = still.size
    if frame.shape[1] != width or frame.shape[0] != height:
        if frame.shape[2] == 4:  # averaged premultiplied, so no colour of nothing bleeds into an edge
            image = Image.fromarray(frame, "RGBA").convert("RGBa").resize((width, height), Image.Resampling.BOX)
            frame = np.asarray(image.convert("RGBA"))
        else:
            frame = np.asarray(Image.fromarray(frame, "RGB").resize((width, height), Image.Resampling.BOX))
    return encode(frame)


# --- a document, held ----------------------------------------------------------------------------


class Held:
    """One document as a renderer holds it (see the module docstring)."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.structure: dict[str, Any] | None = None
        self.version: str | None = None
        self.buffers: dict[str, bytes] = {}
        self.shapes: dict[tuple[str, str], Any] = {}
        self.scenes: dict[bool, Any] = {}  # Preview or not: a scene
        self.kept: dict[bool, list[Any]] = {}  # what Preview's look shows for good (its floor)
        self.last: tuple[dict[str, Any], tuple[int, int]] | None = None  # the modes' last display and size
        # A file read by its reader (``open``): how it poses (a robot's), what it read, what it warned.
        self.kind: str | None = None
        self.poser: Any = None
        self.files: dict[str, Any] = {}
        self.warnings: list[str] = []

    def open(self) -> dict[str, Any]:
        """The file at ``path`` read by its reader (``formats.read``: a mesh file, a robot) and held
        as a document is: what ``hold`` answers, the files read and their stamps, the warnings."""
        from cadgen.engine import formats

        started = time.perf_counter()
        found = formats.read(self.path)
        read = round((time.perf_counter() - started) * 1000)
        self.kind, self.poser, self.files, self.warnings = found.kind, found.pose, found.files, found.warnings
        held = self.hold(found.structure, found.buffers, found.shapes)
        return {**held, "readMs": read, "kind": found.kind, "files": found.files, "warnings": found.warnings}

    def hold(self, structure: dict[str, Any], buffers: dict[str, bytes], shapes: dict[str, Any] | None = None) -> dict[str, Any]:
        """A version of the document: its structure and the meshes of the parts this lacks. The
        shapes of every part it shares with the last are kept and the new are made now (``shapes``:
        those a reader made already, by key: a GLB's textured parts); a scene of the modes that was
        drawn is made again from them now too, its presentations computed for the display it last
        showed, so the next picture waits on neither."""
        from cadgen.engine.mesh import Mesh
        from cadgen.engine.render.occt import prototype_shapes

        started = time.perf_counter()
        keys = {p["key"] for p in structure["prototypes"]}
        kept = {key: data for key, data in {**self.buffers, **buffers}.items() if key in keys}
        missing = sorted(keys - set(kept))
        if missing:  # refused whole: what this holds stays as it was
            raise KeyError(f"no mesh of part{'s' if len(missing) > 1 else ''} {', '.join(missing)}")
        self.buffers = kept
        wanted = {(p["key"], _paints(p)): p for p in structure["prototypes"]}
        made = 0
        for found, prototype in wanted.items():
            if found not in self.shapes:
                given = (shapes or {}).get(found[0])
                self.shapes[found] = given if given is not None else \
                    prototype_shapes(prototype, Mesh.from_bytes(self.buffers[found[0]]))
                made += 1
        for gone in set(self.shapes) - set(wanted):
            del self.shapes[gone]
        again = False
        if structure.get("version") != self.version or self.structure is None:
            again = False in self.scenes and self.last is not None
            self.close()
        self.structure, self.version = structure, structure.get("version")
        if again:
            assert self.last is not None
            display, size = self.last
            scene, _fresh = self._scene(False, size)
            scene.explode(0)
            scene.show(display)
        return {"parts": len(wanted), "made": made, "kept": len(wanted) - made, "scene": again,
                "ms": round((time.perf_counter() - started) * 1000)}

    def close(self) -> None:
        """Let go of the scenes, at once and whole, between pictures: each canvas closed, then the
        scenes collected here and now (a scene collected while another draws takes that one's
        environment map with it). The meshes and shapes stay."""
        if not self.scenes:
            return
        for scene in self.scenes.values():
            scene.clear_overlays()
            scene.canvas.close()
        self.scenes.clear()
        self.kept.clear()
        gc.collect()

    def _scene(self, preview: bool, size: tuple[int, int]) -> tuple[Any, bool]:
        from cadgen.engine.render.occt import Scene

        scene = self.scenes.get(preview)
        if scene is not None:
            return scene, False
        assert self.structure is not None
        parts = [self.shapes[(p["key"], _paints(p))] for p in self.structure["prototypes"]]
        scene = self.scenes[preview] = Scene(self.path, self.buffers, size=size, structure=self.structure, parts=parts)
        return scene, True

    def draw(self, still: Any) -> tuple[bytes, dict[str, Any]]:
        """``still`` (a ``snapshot.Still``) drawn: the PNG's bytes and what was drawn."""
        from cadgen.engine.mechanism import posed_structure
        from cadgen.engine.render.occt import FOCAL_LENGTH
        from cadgen.engine.snapshot import SnapshotRefused, exploded_amount, hidden_instances, refusals

        if self.structure is None:
            raise RuntimeError("the renderer holds no document")
        started = time.perf_counter()
        timings: dict[str, int] = {}
        shown, posed = self.structure, None
        if still.pose is not None:
            if self.kind is not None and self.poser is None:
                raise SnapshotRefused(f"--pose poses a mechanism; {self.path.name} is a mesh and has none")
            try:
                shown = (self.poser or posed_structure)(self.structure, still.pose)
            except ValueError as error:  # mechanism.KinematicsError: what the pose names wrong, by name
                raise SnapshotRefused(f"--pose: {error}") from None
            posed = shown["kinematics"]["pose"]
        refusals(still, shown, self.path.name)
        hidden = hidden_instances(shown, still.display, self.path.name)
        clock = time.perf_counter()
        scene, fresh = self._scene(still.preview, still.drawn)
        if fresh:
            timings["sceneMs"] = round((time.perf_counter() - clock) * 1000)
        scene.canvas.width, scene.canvas.height = still.drawn  # supersampled, brought down after (``picture``)
        # The pose moves the instances: the structure and matrices the scene places them by.
        scene.structure, scene.matrices = shown, [_matrix(instance["matrix"]) for instance in shown["instances"]]
        scene.hidden = hidden  # hidden and isolated parts: every look leaves them out
        clock = time.perf_counter()
        scene.clear_overlays(keep=self.kept.get(still.preview, ()))
        scene.grid(False)
        display = dict(still.display)
        if not still.preview:
            self.last = (display, still.size)
        scene.explode(exploded_amount(display))
        scene.show(display, preview=still.preview)
        timings["presentMs"] = round((time.perf_counter() - clock) * 1000)
        clock = time.perf_counter()
        lens = display.get("camera") or {}
        projection = lens.get("projection") or ("perspective" if still.preview else "orthographic")
        focal_length = float(lens.get("focalLength") or FOCAL_LENGTH)
        camera = still.camera if still.camera is not None else "iso"
        if isinstance(camera, str):
            scene.frame(camera, projection, focal_length, padding=still.padding, tight=still.tight)
            name = camera
        elif still.exact:
            scene.frame(camera, projection, focal_length)  # a view's own camera, placed as it is
            name = "authored"
        else:
            frame_camera(scene, camera, projection, focal_length, still.padding, still.tight)
            name = str(camera.get("name") or "custom")
        if display.get("grid"):
            scene.grid(True)
        if still.annotation:
            scene.annotate(still.annotation)
        if still.measurements:
            scene.measure(still.measurements)
        if still.preview and still.preview not in self.kept:
            before = len(scene.overlays)
            scene.preview_look(0)
            self.kept[True] = scene.overlays[before:]  # what it shows for good (its studio is the scene's)
        elif still.preview:
            scene.restage()  # the floor's shadow follows a pose or Explode
        timings["frameMs"] = round((time.perf_counter() - clock) * 1000)
        clock = time.perf_counter()
        data = picture(scene.canvas, scene.painter(), still, scene.backdrop)
        timings["drawMs"] = round((time.perf_counter() - clock) * 1000)
        timings["renderMs"] = round((time.perf_counter() - started) * 1000)
        unmeshed = {p.get("name") or p["key"]: p["unmeshed"] for p in self.structure["prototypes"] if p.get("unmeshed")}
        return data, {"width": still.size[0], "height": still.size[1], **finished(still), "camera": name,
                      "projection": projection,
                      "displayMode": display.get("mode", "solid"), "preview": still.preview,
                      "parts": len(self.structure["prototypes"]), "instances": len(shown["instances"]),
                      "unmeshed": unmeshed, "pose": posed, "exploded": exploded_amount(display) or None,
                      "renderer": "occt", **({"font": ", ".join(sorted(scene.fonts))} if scene.fonts else {}),
                      **({"kind": self.kind, "warnings": self.warnings} if self.kind else {}), "timings": timings}


def holder(path: Path) -> Any:
    """What holds the file at ``path`` that is no document, for ``open`` and ``draw``: a drawing's
    (a DXF, ``drawing.Held``), else a document's."""
    from cadgen.engine import formats

    if Path(path).suffix.lower() == ".kicad_pcb":
        from cadgen.engine.render.board import Held as Board
        return Board(Path(path))
    if Path(path).suffix.lower() == formats.DRAWING:
        from cadgen.engine.render.drawing import Held as Drawing

        return Drawing(Path(path))
    return Held(Path(path))


def foreign(path: Path) -> bool:
    """Whether ``path`` is a file a reader of ``formats`` reads, not a document the engine serves."""
    from cadgen.engine import formats

    return Path(path).suffix.lower() in formats.KINDS


def draw_here(document: Path, still: Any, *, source: Any = None) -> tuple[bytes, dict[str, Any]]:
    """A document drawn in this process: served by a server of its own (from ``source``, a build's
    document in this process's memory, over its one mesh cache; else read from its file), every
    part meshed there, drawn once. A file no document (``foreign``) is read by its reader, here."""
    [drawn] = draw_here_each(document, [still], source=source)
    return drawn


def _drawn(held: Any, stills: list[Any]) -> list[tuple[bytes, dict[str, Any]]]:
    """Each still drawn from what ``held`` holds, the snapshot's ``draw`` stage said before each
    (``progress.say``: counted when there are several)."""
    from cadgen.engine.progress import say

    drawn = []
    for index, still in enumerate(stills):
        say("draw", count=[index, len(stills)] if len(stills) > 1 else None)
        drawn.append(held.draw(still))
    return drawn


def draw_here_each(document: Path, stills: list[Any], *, source: Any = None) -> list[tuple[bytes, dict[str, Any]]]:
    """``draw_here`` for several stills of one document (a job's pictures of it): served, read and
    meshed once, each still drawn from what was held. Where it is goes to this process's job
    (``progress.say``): ``scene`` while the document is served, meshed and held, ``draw`` as each
    still is drawn."""
    from cadgen.engine.progress import say
    from cadgen.engine.serve import MESHES, Server

    started = time.perf_counter()
    say("scene", detail=document.name)
    if source is None and foreign(document):
        held = holder(document)
        try:
            opened = held.open()
            drawn = _drawn(held, stills)
        finally:
            held.close()
        for _data, report in drawn:
            report["timings"] = {"readMs": opened["readMs"], **report["timings"]}
        return drawn
    if source is not None:
        server = Server(port=0, mesh_mode="inline", cache=MESHES)
        ident = server.put(document, source.structure,
                           {p["key"]: source.shape_data(p["key"]) for p in source.structure["prototypes"]})
    else:
        server = Server(port=0)
    try:
        if source is None:
            ident = server.add(document)
        doc = server.document(ident)
        served = time.perf_counter()
        meshed = server.mesh_all(doc, None)
        structure = server.structure(doc)
        buffers = {p["key"]: server.cache.get(p["key"]) for p in structure["prototypes"]}
    finally:
        server.stop()
    held = Held(document)
    try:
        timings = {"serveMs": round((served - started) * 1000), "meshMs": round((time.perf_counter() - served) * 1000)}
        held.hold(structure, buffers)
        drawn = _drawn(held, stills)
    finally:
        held.close()
    for _data, report in drawn:
        report["timings"] = {**timings, **report["timings"]}
        report["mesh"] = {key: meshed.get(key) for key in ("parts", "meshed", "seconds", "triangles", "mode")}
    return drawn


# --- the render process ------------------------------------------------------------------------------


def _read(stream: Any) -> tuple[dict[str, Any], bytes] | None:
    """One frame: a JSON line and the bytes it says follow; None at the end of the stream."""
    while True:
        line = stream.readline()
        if not line:
            return None
        if line.strip().startswith(b"{"):
            break
    message = json.loads(line)
    size = int(message.get("bytes") or 0)
    chunks, left = [], size
    while left:
        chunk = stream.read(left)
        if not chunk:
            raise EOFError("the stream ended inside a frame")
        chunks.append(chunk)
        left -= len(chunk)
    return message, b"".join(chunks)


def _write(stream: Any, message: dict[str, Any], payload: bytes = b"") -> None:
    if payload:
        message = {**message, "bytes": len(payload)}
    stream.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
    if payload:
        stream.write(payload)
    stream.flush()


def main() -> int:
    """The render process: one served document, held warm, drawn on request."""
    sys.dont_write_bytecode = True
    protocol = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)  # anything printed goes where the daemon reads logs from
    sys.stdout = sys.stderr
    from cadgen.engine.formats import FormatError
    from cadgen.engine.render.context import pool
    from cadgen.engine.snapshot import SnapshotRefused, Still
    from cadgen.engine.worker import resident_mb, rss_cap_mb

    _write(protocol, {"ready": os.getpid()})
    # Collected between requests alone: nothing of a scene is let go of while one draws.
    gc.disable()
    held: Held | None = None
    frames = 0
    while True:
        gc.collect()
        found = _read(sys.stdin.buffer)
        if found is None:
            break
        request, payload = found
        ident, op = request.get("id"), request.get("op")
        try:
            if op == "hold":
                buffers, at = {}, 0
                for key, size in request.get("meshes") or []:
                    buffers[key] = payload[at:at + size]
                    at += size
                if held is None or held.path != Path(request["path"]) or getattr(held, "kind", None):
                    if held is not None:
                        held.close()
                    held = Held(Path(request["path"]))
                with pool():
                    _write(protocol, {"id": ident, "held": held.hold(request["structure"], buffers)})
                continue
            if op == "open":  # a file no document, read by its reader here
                if held is not None:
                    held.close()
                held = None
                opened = holder(Path(request["path"]))
                with pool():
                    answer = opened.open()
                held = opened
                _write(protocol, {"id": ident, "opened": answer})
                continue
            if op != "frame":
                _write(protocol, {"id": ident, "failed": f"unknown request {op!r}"})
                continue
            if held is None:
                raise RuntimeError("the renderer holds no document")
            with pool():
                data, report = held.draw(Still.from_json(request["still"]))
            frames += 1
            resident, cap = resident_mb(), rss_cap_mb()
            report["process"] = {"pid": os.getpid(), "frames": frames, "rssMb": None if resident is None else round(resident)}
            retire = resident is not None and cap is not None and resident > cap
            if retire:
                report["retired"] = (f"the renderer held {resident:.0f} MB after the frame, over its {cap:.0f} MB cap "
                                     "(CADGEN_ENGINE_WORKER_RSS_MB): the next snapshot starts a fresh one")
            _write(protocol, {"id": ident, "done": report}, data)
            if retire:
                return 0
        except (SnapshotRefused, FormatError) as error:
            _write(protocol, {"id": ident, "refused": str(error)})
        except Exception as error:  # noqa: BLE001 - the renderer answers every request
            _write(protocol, {"id": ident, "failed": "".join(traceback.format_exception_only(type(error), error)).strip(),
                              "trace": traceback.format_exc()})
    return 0


# --- the daemon's side ---------------------------------------------------------------------------------


class Gone(RuntimeError):
    """A render process that exited (or never started)."""


class Refused(ValueError):
    """A request the document does not offer, refused by name before anything was drawn."""


class RenderProcess:
    """One served document's render process, from the daemon's side: started on its document's
    first snapshot; the version it holds and the parts whose meshes it was sent."""

    def __init__(self, path: Path, environment: dict[str, str]) -> None:
        from cadgen.engine.daemon import engine_root, windowless

        env = dict(environment)
        root = engine_root()
        if root not in env.get("PYTHONPATH", "").split(os.pathsep):
            env["PYTHONPATH"] = os.pathsep.join(item for item in (root, env.get("PYTHONPATH", "")) if item)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        self.path = Path(path)
        self.process = subprocess.Popen([sys.executable, "-P", "-m", "cadgen.engine.render.service"],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                        **windowless())
        self.lock = threading.Lock()
        self.version: str | None = None
        self.keys: set[str] = set()
        self.frames = 0
        self.rss: int | None = None
        self.retired = False
        self.used = time.monotonic()  # when it last drew: the memory cap retires the least recently drawn first
        self.meshed: dict[str, Any] | None = None  # the engine's account of the meshing its last version took
        self.held: dict[str, Any] | None = None  # what it made and kept of its last version's parts
        self.files: dict[str, Any] = {}  # a file no document: every file its reader read, stamped
        self.said: list[str] = []  # its last lines on stderr, for a failure's report
        threading.Thread(target=self._stderr, daemon=True).start()
        ready = _read(self.process.stdout)
        if ready is None or "ready" not in ready[0]:
            raise Gone(f"the renderer for {self.path.name} did not start: {self._last()}")
        self.pid = ready[0]["ready"]

    def _stderr(self) -> None:
        assert self.process.stderr is not None
        try:
            for line in iter(self.process.stderr.readline, b""):
                self.said = [*self.said[-40:], line.decode("utf-8", "replace").rstrip()]
        except (OSError, ValueError):  # closed by ``stop``
            pass

    def _last(self) -> str:
        return " | ".join(line for line in self.said[-5:] if line) or "no word from it"

    def alive(self) -> bool:
        return self.process.poll() is None and not self.retired

    def busy(self) -> bool:
        """Whether it is drawing or being sent a version now: never retired then."""
        return self.lock.locked()

    def ask(self, request: dict[str, Any], payload: bytes = b"") -> tuple[dict[str, Any], bytes]:
        """One request and its answer (call with ``lock`` held)."""
        try:
            _write(self.process.stdin, request, payload)
            found = _read(self.process.stdout)
        except (OSError, ValueError, EOFError) as error:
            raise Gone(f"the renderer for {self.path.name} is gone ({error}): {self._last()}") from None
        if found is None:
            code = self.process.wait()
            raise Gone(f"the renderer for {self.path.name} exited ({code}): {self._last()}")
        return found

    def stop(self) -> None:
        try:
            if self.process.stdin is not None:
                self.process.stdin.close()
            self.process.wait(timeout=5)
        except Exception:  # noqa: BLE001
            self.process.kill()
            self.process.wait()
        for stream in (self.process.stdout, self.process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass


class Renders:
    """The daemon's render processes: one per served document, by its id on the server."""

    def __init__(self, server: Any, environment: Callable[[], dict[str, str]] = lambda: dict(os.environ)) -> None:
        self.server = server
        self.environment = environment
        self.processes: dict[str, RenderProcess] = {}
        self.lock = threading.Lock()

    def _process(self, ident: str, path: Path) -> RenderProcess:
        with self.lock:
            found = self.processes.get(ident)
            if found is not None and found.alive():
                return found
            if found is not None:
                found.stop()
            found = self.processes[ident] = RenderProcess(path, self.environment())
            return found

    def _sync(self, render: RenderProcess, doc: Any) -> dict[str, int]:
        """The process holds the served version: every part meshed (the daemon's pool, for any
        part its cache lacks), and the buffers of the parts the process lacks sent with the
        structure. Call with the process's lock held."""
        timings: dict[str, int] = {}
        if render.version == doc.version:
            return timings
        clock = time.perf_counter()
        meshed = self.server.mesh_all(doc, None)
        structure = self.server.structure(doc)
        timings["meshMs"] = round((time.perf_counter() - clock) * 1000)
        clock = time.perf_counter()
        lacking = sorted({p["key"] for p in structure["prototypes"]} - render.keys)
        buffers = []
        for key in lacking:
            data = self.server.cache.get(key)
            if data is None:  # dropped from the cache since: meshed again from the document's shape
                data = self.server._submit(key, self.server.shape_of(doc, key), None).result()[0]
            buffers.append(data)
        answer, _payload = render.ask({"op": "hold", "path": str(doc.path), "structure": structure,
                                       "meshes": [[key, len(data)] for key, data in zip(lacking, buffers)]},
                                      b"".join(buffers))
        if "held" not in answer:
            raise RuntimeError(answer.get("failed") or "the renderer would not hold the document")
        render.version, render.keys, render.held = doc.version, {p["key"] for p in structure["prototypes"]}, answer["held"]
        timings["holdMs"] = round((time.perf_counter() - clock) * 1000)
        render.meshed = {key: meshed.get(key) for key in ("parts", "meshed", "seconds", "triangles", "mode")}
        return timings

    def _file(self, path: Path, still: dict[str, Any], progress: Any = None) -> tuple[bytes, dict[str, Any]]:
        """A picture of a file no document (``foreign``): its render process, which reads it with
        its reader, opened again whenever a file it read has changed, asked for a frame. ``progress``
        as ``draw`` takes it."""
        from cadgen.engine.formats import stale

        timings: dict[str, int] = {}
        if progress is not None:
            progress.stage("scene", detail=path.name)
        for attempt in (1, 2):
            render = self._process(f"file:{path}", path)
            try:
                with render.lock:
                    if render.version is None or stale(render.files):
                        clock = time.perf_counter()
                        answer, _payload = render.ask({"op": "open", "path": str(path)})
                        if "refused" in answer:
                            raise Refused(answer["refused"])
                        if "opened" not in answer:
                            raise RuntimeError(answer.get("failed") or f"the renderer could not read {path.name}")
                        opened = answer["opened"]
                        render.version, render.files, render.held = "opened", opened["files"], opened
                        timings.update(openMs=round((time.perf_counter() - clock) * 1000), readMs=opened["readMs"])
                    if progress is not None:
                        progress.stage("draw")
                    answer, data = render.ask({"op": "frame", "still": still})
            except Gone:
                if attempt == 2:
                    raise
                continue
            break
        if "refused" in answer:
            raise Refused(answer["refused"])
        if "done" not in answer:
            raise RuntimeError(answer.get("failed") or "the renderer drew nothing")
        report = answer["done"]
        render.frames += 1
        render.rss = (report.get("process") or {}).get("rssMb")
        if report.get("retired"):
            render.retired = True
        report["timings"] = {**timings, **report.get("timings", {})}
        return data, report

    def draw(self, path: Path, still: dict[str, Any], progress: Any = None) -> tuple[bytes, dict[str, Any]]:
        """A picture of the served document at ``path``: its render process started, or patched
        to the version served, and asked for a frame. Raises ``Refused`` by name. A file no
        document is read and drawn by a render process of its own (``_file``). ``progress``, a
        ``progress.Progress`` of kind ``snapshot``, is told the stages as they begin: ``scene`` while
        the document is served, meshed and held by its process, ``draw`` while the frame is drawn."""
        if foreign(Path(path)):
            return self._file(Path(path).resolve(), still, progress)
        started = time.perf_counter()
        if progress is not None:
            progress.stage("scene", detail=Path(path).name)
        ident = self.server.add(Path(path))
        doc = self.server.document(ident)
        timings = {"serveMs": round((time.perf_counter() - started) * 1000)}
        for attempt in (1, 2):
            render = self._process(ident, doc.path)
            try:
                with render.lock:
                    timings.update(self._sync(render, doc))
                    if progress is not None:
                        progress.stage("draw")
                    answer, data = render.ask({"op": "frame", "still": still})
            except Gone:
                if attempt == 2:
                    raise
                continue
            break
        if "refused" in answer:
            raise Refused(answer["refused"])
        if "done" not in answer:
            raise RuntimeError(answer.get("failed") or "the renderer drew nothing")
        report = answer["done"]
        render.frames += 1
        render.used = time.monotonic()
        render.rss = (report.get("process") or {}).get("rssMb")
        if report.get("retired"):
            render.retired = True
        report["timings"] = {**timings, **report.get("timings", {})}
        report["mesh"] = render.meshed
        return data, report

    def status(self) -> list[dict[str, Any]]:
        return [{"document": str(render.path), "pid": render.pid, "version": render.version, "held": render.held,
                 "frames": render.frames, "rssMb": render.rss, "alive": render.alive(), "busy": render.lock.locked()}
                for render in self.processes.values()]

    def processes_now(self) -> list[RenderProcess]:
        """The render processes alive now, whose memory the workers' cap counts (``daemon.Pool.shed``):
        read without the lock, which is held while a process starts."""
        return [render for render in list(self.processes.values()) if render.alive()]

    def retire(self, render: RenderProcess) -> None:
        """One render process stopped for memory (``daemon.Pool.shed``), unless it is drawing: the next
        snapshot of its document starts another."""
        with self.lock:
            ident = next((ident for ident, found in self.processes.items() if found is render), None)
            if ident is None or render.busy():
                return
            del self.processes[ident]
        render.stop()

    def stop(self) -> None:
        with self.lock:
            for render in self.processes.values():
                render.stop()
            self.processes.clear()


def answer_png(data: bytes) -> str:
    """A picture as the daemon's answer carries it on its JSON line."""
    return base64.b64encode(data).decode("ascii")


if __name__ == "__main__":
    sys.exit(main())
