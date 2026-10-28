"""PROTOTYPE: an engine document drawn by OCCT's own OpenGL renderer, from the engine's meshes.

``python -m cadgen.engine.render.occt DOC.xbf OUT.png [--display MODE|JSON] [--camera C|JSON] [--grid]
[--preview] [--pose NAME|JSON] [--explode AMOUNT] [--annotation FILE] [--measurements FILE]
[--path-trace N] [--mesh-cache DIR] [--width W --height H] [--json]``

The flags are ``cadgen snapshot``'s where it has them, and mean what the viewer means:

- The document is read (``document.Loaded``: structure, names, colours, the mechanism) and every
  part's mesh is the engine's XBM buffer -- from the daemon, or a folder of them -- turned into
  triangulation-only faces and polygon edges (``shapes.py``). OCCT meshes nothing.
- One presentation per part and look (``AIS_Shape``), placed per instance by
  ``AIS_ConnectedInteractive``: an instance shares its part's arrays, as the viewer's instances do.
- Modes as the viewer's Display menu (``viewSettings.js``): solid (faces and every CAD edge),
  shaded (faces), parts (solid, each instance a colour of the workbench palette), xray (faces at
  0.22 opacity, every edge over them), hidden-line (faces in the backdrop's colour hiding the edges
  behind them), wireframe (every edge).
- Camera as the snapshot page's (``renderMeshScene.js``): a preset's or ``az:el``'s direction,
  orthographic with the tight frame (every placed vertex projected, padding 0.04), or perspective
  (``display.camera.projection``, 48 degrees, the same tight fit); or a prompt view's camera
  (``{position, target, up, orthographicHalfHeight}``, JSON or a file), placed as it is.
- ``--pose``: the engine's forward kinematics (``mechanism.posed_structure``); ``--explode``: the
  viewer's own explode layout (``explode.py``); ``display.clip``: an OCCT clip plane, its cut
  capped as the viewer caps it (``clip.py``); ``--annotation`` and ``--measurements``: the
  snapshot job's ``annotation`` and ``measurements`` data, drawn as the viewer draws them:
  strokes as screen-width strips, a text mark's words (the viewer's face, set and rasterised as
  its canvas is, ``text.py``) on its quad, Measure's dimensions painted over the frame in screen
  space (``overlay.py``).
- ``--preview``: physically based raster (PBR, an image-based environment, a key light with
  shadows on a floor that runs past the frame, the backdrop the floor's own colour as drawn, so
  the two meet without an edge), a part with a material in the material the modes draw it in
  (``finish.py``); ``--path-trace N``: OCCT's path tracer, N samples.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from cadgen.engine.mesh import Mesh
from cadgen.engine.render.context import Canvas
from cadgen.engine.render.look import LOOK
from cadgen.engine.render.shapes import LINES, FaceGroup, prototype_shapes

MODES = ("solid", "shaded", "parts", "xray", "hidden-line", "wireframe")
PRESETS = {
    "front": ((0, -1, 0), (0, 0, 1)), "back": ((0, 1, 0), (0, 0, 1)), "right": ((1, 0, 0), (0, 0, 1)),
    "left": ((-1, 0, 0), (0, 0, 1)), "top": ((0, 0, 1), (0, 1, 0)), "bottom": ((0, 0, -1), (0, 1, 0)),
    "iso": ((1, -1, 0.8), (0, 0, 1)),
}
# The regular modes' numbers are the look's (``look.py``), which the viewer draws by too.
BACKGROUND = LOOK.backdrop
EDGE = dict(LOOK.edge_colours)
DEFAULT_FILL = LOOK.fill
PARTS = LOOK.palette
REFERENCE_HEIGHT = 900  # an annotation's ink is as heavy against the picture as on a viewer this tall
PADDING = 0.04
FOCAL_LENGTH = 50.0  # the view's default camera.focalLength (viewSettings.js), on three's 35 mm film gauge
# The studio environment's horizon grey (sRGB, as its cube map holds it), which lights the model.
HORIZON = (0.70, 0.71, 0.73)
# Preview's studio is the viewer's, light (viewSettings.js previewDefaults, photographicStudioRig.js):
# the backdrop white, lifted toward white behind the middle of the frame and shaded toward its
# corners (a dark and a light colour's share) and above the horizon (studioBackdrop.js);
BACKDROP = "#ffffff"
BACKDROP_LIFT, BACKDROP_SHADE, BACKDROP_WALL = 0.07, (0.38, 0.1), 0.6
# the floor at the model's lowest point, #e7e7e5 at 60%, full to 1.6 of the model's reach and gone at 6.
# OCCT draws it unlit in the colour the viewer's Preview draws it (its #e7e7e5 lit by the studio and
# tone-mapped), read off the viewer's own Preview pictures;
FLOOR_COLOUR = "#ececea"
FLOOR_OPACITY = 0.6
FLOOR_FADE = (1.6, 6.0)
# the floor's shadow (studioContactShadow.js): its square reaching 0.85 of the model's height past its
# footprint, occlusion reaching 0.5 of that height; contact, occlusion and the key's shadow near
# and far at these strengths, blurred narrow, medium and wide by these shares of the square; the
# key the viewer's (rotation 0). Baked here at SHADOW_TEXELS a side (the viewer: 512, the same blurs).
CONTACT_REACH, CONTACT_HEIGHT = 0.85, 0.5
CONTACT_STRENGTH = (0.75, 0.5, 0.75, 0.35)
CONTACT_BLUR = (0.012, 0.03, 0.06)
KEY_DIRECTION = (-0.35, -1.0, 1.5)
SHADOW_TEXELS = 160


def occt_scale(height: float, aspect: float) -> float:
    """OCCT's orthographic scale for a view ``height`` tall: the scale is the view's height, or its
    width when the picture is taller than wide."""
    return height if aspect >= 1 else height * aspect


def occt_fov(fov: float, aspect: float) -> float:
    """OCCT's field of view for a vertical one of ``fov`` degrees: like its scale, OCCT's field of
    view spans the width when the picture is taller than wide."""
    return fov if aspect >= 1 else math.degrees(2 * math.atan(math.tan(math.radians(fov) / 2) * aspect))


def vertical_fov(aspect: float, focal_length: float = FOCAL_LENGTH) -> float:
    """three's ``PerspectiveCamera.setFocalLength``: the film's height is the gauge over the aspect."""
    return math.degrees(2 * math.atan(0.5 * (35.0 / max(aspect, 1.0)) / focal_length))


def _color(value: Any) -> Any:
    """A ``#rrggbb`` (sRGB, as CSS) or an rgb(a) tuple (linear, as the document and three hold it)."""
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB, Quantity_TOC_sRGB

    if isinstance(value, str):
        value = value.lstrip("#")
        value = [int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        return Quantity_Color(float(value[0]), float(value[1]), float(value[2]), Quantity_TOC_sRGB)
    return Quantity_Color(float(value[0]), float(value[1]), float(value[2]), Quantity_TOC_RGB)


def _matrix(values: list[float]) -> np.ndarray:
    return np.array(values, float).reshape(4, 4).T  # column-major, as WebGL reads it


def _trsf(matrix: np.ndarray) -> Any:
    from OCP.gp import gp_Trsf

    trsf = gp_Trsf()
    m = matrix
    trsf.SetValues(m[0, 0], m[0, 1], m[0, 2], m[0, 3], m[1, 0], m[1, 1], m[1, 2], m[1, 3],
                   m[2, 0], m[2, 1], m[2, 2], m[2, 3])
    return trsf


def direction_of(camera: str) -> tuple[np.ndarray, np.ndarray]:
    """A preset's or ``azimuth:elevation``'s direction (target to eye) and up, as ``camera.js``."""
    if camera in PRESETS:
        direction, up = PRESETS[camera]
    else:
        azimuth, elevation = (math.radians(float(part)) for part in camera.split(":"))
        direction = (math.sin(azimuth) * math.cos(elevation), -math.cos(azimuth) * math.cos(elevation),
                     math.sin(elevation))
        up = (0, 0, 1)
    d = np.array(direction, float)
    return d / np.linalg.norm(d), np.array(up, float)


def camera_in_millimetres(camera: dict[str, Any], factor: float) -> dict[str, Any]:
    """A camera object's lengths -- ``position``, ``target`` and ``orthographicHalfHeight`` -- in the
    scene's millimetres, from the viewer's scene coordinates (``factor`` millimetres each:
    ``Scene.millimetres_per_scene_unit``), which a Quick Edit packet's view carries and ``--camera``
    takes: a document's and a GLB's millimetres, a robot's metres, a 3MF's declared unit. ``up``,
    ``direction``, ``zoom``, ``preset`` and ``name`` carry no length. The camera itself at 1."""
    if factor == 1.0:
        return camera
    scaled = dict(camera)
    for key in ("position", "target"):
        if camera.get(key) is not None:
            scaled[key] = [float(value) * factor for value in camera[key]]
    if camera.get("orthographicHalfHeight") is not None:
        scaled["orthographicHalfHeight"] = float(camera["orthographicHalfHeight"]) * factor
    return scaled



class Scene:
    """A document on a canvas: its parts as shapes, one presentation per part and look, an
    instance a connected object of it. ``parts``: each prototype's ``prototype_shapes`` already
    made, by index (a warm renderer's, ``service.py``), else made here."""

    def __init__(self, path: Path, buffers: dict[str, bytes], *, size: tuple[int, int] = (1600, 1200),
                 structure: dict[str, Any] | None = None, pose: Any = None, parts: list[Any] | None = None) -> None:
        self.timings: dict[str, float] = {}
        clock = time.perf_counter()
        self.path = Path(path)
        if structure is None:
            from cadgen.engine.document import Loaded

            structure = Loaded(self.path).structure()
        self.rest_structure = structure
        if pose is not None:
            from cadgen.engine.mechanism import posed_structure

            structure = posed_structure(structure, pose)
        self.structure = structure
        # The millimetres one of the file's units is (``formats.assemble``): a document's are millimetres
        # (1), a robot's and a GLB's metre 1000. A length asked of the file -- where ``display.clip.at``
        # stands -- is in that unit, as the viewer reads one (``sceneUnits.js``).
        self.millimetres_per_unit = float(structure.get("millimetresPerUnit") or 1.0)
        # And one of the viewer's scene coordinates: the file's unit, but a GLB's millimetre (the viewer
        # draws glTF's metres as millimetres). A Quick Edit packet's camera, Measure's points and the ink
        # are in those coordinates (``camera_in_millimetres``, ``measure``, ``annotate``).
        self.millimetres_per_scene_unit = float(structure.get("millimetresPerSceneUnit") or self.millimetres_per_unit)
        self.timings["read"] = time.perf_counter() - clock
        clock = time.perf_counter()
        self.canvas = Canvas(*size)
        self.timings["context"] = time.perf_counter() - clock
        clock = time.perf_counter()
        self.prototypes = structure["prototypes"]
        self.meshes = {p["key"]: Mesh.from_bytes(buffers[p["key"]]) for p in self.prototypes}
        self.parts = list(parts) if parts is not None else [prototype_shapes(p, self.meshes[p["key"]])
                                                            for p in self.prototypes]
        self.timings["shapes"] = time.perf_counter() - clock
        self.matrices = [_matrix(instance["matrix"]) for instance in structure["instances"]]
        self.rest = [_matrix(instance["matrix"]) for instance in self.rest_structure["instances"]]
        self.boxes = {}
        for index, prototype in enumerate(self.prototypes):
            positions = self.meshes[prototype["key"]].positions
            if len(positions):
                self.boxes[index] = (positions.min(0).astype(float), positions.max(0).astype(float))
        self.offsets: dict[int, np.ndarray] = {}
        self.sources: dict[tuple, Any] = {}
        self.shown: list[Any] = []
        # The instances a picture leaves out (``display.hidden``, ``display.isolated``): not
        # shown, framed, capped or shadowed.
        self.hidden: frozenset[int] = frozenset()
        self.carriers: dict[int, Any] = {}  # each prototype's cap carrier, made on the first clip (``clip.py``)
        self.caps: list[Any] = []  # the carriers shown, each an instance's (``clip.py``)
        self.overlays: list[Any] = []
        self.structures: list[Any] = []  # presentations made below AIS: the text quads
        self.text_quads: list[tuple[np.ndarray, str]] = []  # their world corners and colours
        self.screen_marks: list[dict[str, Any]] = []  # painted over the frame: Measure's
        self.fonts: set[str] = set()  # the faces the words of the frame were set in (text.face_source)
        self.stage: list[Any] = []  # Preview's studio: its floor and the floor's shadow
        self.studio = False
        self.staged = b""  # the placements its shadow was baked for
        self.mode = None
        self.display: dict[str, Any] = {}
        self.preview = False
        self.colour_only = False  # the view's rig: X-ray's colour-only one, else the look's own
        self._setup_view()

    # --- the view ------------------------------------------------------------------------

    def _setup_view(self) -> None:
        from cadgen.engine.render.finish import put_up

        view = self.canvas.view
        viewer = self.canvas.viewer
        self.lights = put_up(view, viewer, _color(BACKGROUND))  # the look's PBR rig: its key, its environment
        params = view.ChangeRenderingParams()
        params.NbMsaaSamples = 8
        drawer = self.canvas.context.DefaultDrawer()
        drawer.SetAutoTriangulation(False)  # never mesh: every face carries the engine's triangles
        drawer.SetFaceBoundaryDraw(False)
        # The Top layer holds the annotation's ink: tested against the model's depth, writing none,
        # as the viewer's ink is (``annotation.js``: depthTest, no depthWrite, after the model).
        from OCP.Graphic3d import Graphic3d_ZLayerId_Top

        settings = viewer.ZLayerSettings(Graphic3d_ZLayerId_Top)
        settings.SetEnableDepthTest(True)
        settings.SetEnableDepthWrite(False)
        viewer.SetZLayerSettings(Graphic3d_ZLayerId_Top, settings)

    def _rig(self, colour_only: bool) -> None:
        """The view lit for what is shown: X-ray's colour-only rig (Phong, ``finish.put_up_colour_only``)
        or the look's own (PBR, ``finish.put_up``), the lights of the other taken down."""
        if colour_only == self.colour_only:
            return
        from cadgen.engine.render.finish import put_up, put_up_colour_only

        view, viewer = self.canvas.view, self.canvas.viewer
        for light in self.lights:
            viewer.DelLight(light)
        self.lights = put_up_colour_only(view, viewer) if colour_only else put_up(view, viewer, _color(BACKGROUND))
        self.colour_only = colour_only

    # --- sources: one presentation per part and look ----------------------------------------

    def _material(self, rgba: Any, look: str) -> Any:
        from OCP.Graphic3d import Graphic3d_MaterialAspect, Graphic3d_NameOfMaterial, Graphic3d_PBRMaterial
        from OCP.Quantity import Quantity_ColorRGBA

        material = Graphic3d_MaterialAspect(Graphic3d_NameOfMaterial.Graphic3d_NameOfMaterial_Plastified)
        color = _color(rgba[:3] if rgba is not None and not isinstance(rgba, str) else (rgba or DEFAULT_FILL))
        material.SetColor(color)
        material.SetAmbientColor(color)
        material.SetDiffuseColor(color)
        material.SetSpecularColor(_color((LOOK.xray.specular,) * 3))
        material.SetShininess(LOOK.xray.shininess)
        pbr = Graphic3d_PBRMaterial()
        pbr.SetColor(Quantity_ColorRGBA(color, 1.0))
        pbr.SetMetallic(0.0)
        pbr.SetRoughness(0.5)
        material.SetPBRMaterial(pbr)
        return material, color

    def _faces(self, index: int, group: Any, rgba: Any, look: str) -> Any:
        key = ("faces", index, group, rgba, look)
        found = self.sources.get(key)
        if found is not None:
            return found
        from OCP.AIS import AIS_Shape
        from OCP.Aspect import Aspect_PolygonOffsetMode
        from OCP.Graphic3d import Graphic3d_TypeOfShadingModel

        source = AIS_Shape(self.parts[index].faces[group])
        from cadgen.engine.render.finish import face_material, linear

        fill = isinstance(rgba, str)  # a fill (Parts) paints over a part's texture as over its colour
        own = None if isinstance(rgba, str) else self._material_of(index, group)
        if look in ("hidden", "xray") or (look == "pbr" and own is None):
            # Hidden line's faces hide what is behind them whatever their finish (the viewer's are
            # depth alone), so they are opaque; X-ray's are the colour-only model's, a material its
            # colour alone (``look.py``), drawn by Phong; Preview's surface without a material is its own.
            material, color = self._material(rgba, look)
        else:  # the part's material as the look draws it (``finish.py``): in Preview as in the modes
            if isinstance(rgba, str):  # a fill (Parts) keeps the part's opacity, as the viewer's does
                part = self.prototypes[index].get("color") or ()
                rgba = (*linear(rgba), float(part[3]) if len(part) > 3 else 1.0)
            material, color = face_material(rgba, own)
        source.SetMaterial(material)
        source.SetColor(color)
        aspect = source.Attributes().ShadingAspect().Aspect()
        aspect.SetPolygonOffsets(Aspect_PolygonOffsetMode.Aspect_POM_Fill, 1.0, 1.0)
        texture = self.parts[index].textures.get(group) if look in ("lit", "pbr") and not fill else None
        if texture is not None:  # a GLB's base colour texture, over its material's colour
            aspect.SetTextureSet(texture)
            aspect.SetTextureMapOn(True)
        if look == "hidden":
            source.SetColor(_color(BACKGROUND))
            aspect.SetShadingModel(Graphic3d_TypeOfShadingModel.Graphic3d_TypeOfShadingModel_Unlit)
        elif look == "xray":
            source.SetTransparency(1 - LOOK.mode("xray").opacity)
        self.sources[key] = source
        return source

    def _material_of(self, index: int, group: Any) -> Any:
        """The structure's material for a part's face group: the part's, or a paint's own."""
        prototype = self.prototypes[index]
        if group is None:
            return prototype.get("material")
        if isinstance(group, FaceGroup):
            return self.parts[index].materials.get(group)
        paints = prototype.get("faceMaterials") or {}
        ordinal = next((key for key, value in (prototype.get("faceColors") or {}).items() if tuple(value) == group), None)
        return paints.get(ordinal)  # a paint without a material of its own is its colour alone, as the viewer's

    def _edges(self, index: int, line: str) -> Any:
        key = ("edges", index, line)
        found = self.sources.get(key)
        if found is None:
            from OCP.AIS import AIS_Shape

            found = AIS_Shape(self.parts[index].edges[line])
            found.SetColor(_color(EDGE[line]))
            found.SetWidth(LOOK.edge_width)
            self.sources[key] = found
        return found

    # --- what is shown ----------------------------------------------------------------------

    def placement(self, index: int) -> np.ndarray:
        matrix = self.matrices[index]
        offset = self.offsets.get(index)
        if offset is not None:
            matrix = matrix.copy()
            matrix[:3, 3] += offset
        return matrix

    def show(self, display: dict[str, Any] | None = None, *, preview: bool = False) -> float:
        """Show every instance in ``display``'s mode (or Preview's look); the seconds it took to
        build what is shown (presentations computed on first use, then shared)."""
        from OCP.AIS import AIS_ConnectedInteractive
        from OCP.Graphic3d import Graphic3d_ZLayerId_Topmost

        clock = time.perf_counter()
        display = dict(display or {})
        mode = "solid" if preview else display.get("mode", "solid")
        context = self.canvas.context
        for shown in self.shown:
            context.Remove(shown, False)
        self.shown = []
        self.mode, self.display, self.preview = mode, display, preview
        look = "hidden" if mode == "hidden-line" else "xray" if mode == "xray" else "pbr" if preview else "lit"
        if not preview:  # Preview's look puts up its own (``preview_look``)
            self._rig(look == "xray")
        faces = mode != "wireframe"
        edges = not preview and mode != "shaded"
        on_top = mode in ("xray", "wireframe")
        for index, instance in enumerate(self.structure["instances"]):
            if index in self.hidden:
                continue
            p = instance["prototype"]
            part = self.parts[p]
            trsf = _trsf(self.placement(index))
            rgba = instance.get("color") or self.prototypes[p].get("color")
            rgba = tuple(rgba) if rgba else None
            if mode == "parts":
                rgba = PARTS[instance.get("palette", index) % len(PARTS)]
            if faces:
                for group in part.faces:
                    color = rgba if group is None or mode == "parts" else (
                        (group.color if group.color is not None else rgba)
                        if isinstance(group, FaceGroup) else group)
                    connected = AIS_ConnectedInteractive()
                    connected.Connect(self._faces(p, group, color, look), trsf)
                    context.Display(connected, 1, -1, False)
                    self.shown.append(connected)
            if edges:
                for line in LINES:
                    if line not in part.edges:
                        continue
                    connected = AIS_ConnectedInteractive()
                    connected.Connect(self._edges(p, line), trsf)
                    context.Display(connected, 0, -1, False)
                    if on_top:
                        context.SetZLayer(connected, Graphic3d_ZLayerId_Topmost)
                    self.shown.append(connected)
        self._clip(display.get("clip"))
        seconds = time.perf_counter() - clock
        self.timings["present"] = seconds
        return seconds

    # --- clip --------------------------------------------------------------------------------

    def rest_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        from cadgen.engine.render.explode import placed_box

        boxes = [placed_box(self.boxes[i["prototype"]], m) for i, m in zip(self.rest_structure["instances"], self.rest)
                 if i["prototype"] in self.boxes]
        return np.min([b[0] for b in boxes], 0), np.max([b[1] for b in boxes], 0)

    def _clip(self, clip: dict[str, Any] | None) -> None:
        """``display.clip``: one plane along an axis, at ``at`` (else the middle of the model at
        rest), keeping the lower side (``invert`` the upper), its cut capped as the viewer caps it
        (``clip.py``)."""
        from cadgen.engine.render import clip as section

        section.apply(self, clip)

    # --- camera ------------------------------------------------------------------------------

    def placed_points(self) -> np.ndarray:
        chunks = []
        for index, instance in enumerate(self.structure["instances"]):
            if index in self.hidden:
                continue
            positions = self.meshes[self.prototypes[instance["prototype"]]["key"]].positions
            if len(positions):
                m = self.placement(index)
                chunks.append(positions.astype(float) @ m[:3, :3].T + m[:3, 3])
        return np.concatenate(chunks)

    def _pinned(self, camera: dict[str, Any], projection: str, focal_length: float) -> dict[str, Any]:
        """A camera as a prompt's view holds it (``{position, target, up, orthographicHalfHeight}``,
        ``annotation/views.js``, its lengths in the viewer's scene coordinates: ``camera_in_millimetres``),
        placed as it is, the way the snapshot page places one (``fitOrthographicCamera``: the
        half-height the vertical half-extent, no fit, no padding)."""
        from OCP.gp import gp_Dir, gp_Pnt
        from OCP.Graphic3d import Graphic3d_Camera

        camera = camera_in_millimetres(camera, self.millimetres_per_scene_unit)
        eye, target = np.array(camera["position"], float), np.array(camera["target"], float)
        up = np.array(camera.get("up") or (0.0, 0.0, 1.0), float)
        d = (eye - target) / (np.linalg.norm(eye - target) or 1.0)
        right = np.cross(-d, up)
        right /= np.linalg.norm(right) or 1.0
        screen_up = np.cross(right, -d)
        aspect = self.canvas.width / self.canvas.height
        cam = self.canvas.view.Camera()
        cam.SetAspect(aspect)  # the picture's, so what projects through the camera lands where it is drawn
        scale = None
        if projection == "perspective":
            cam.SetProjectionType(Graphic3d_Camera.Projection_e.Projection_Perspective)
            cam.SetFOVy(occt_fov(vertical_fov(aspect, focal_length), aspect))
        else:
            cam.SetProjectionType(Graphic3d_Camera.Projection_e.Projection_Orthographic)
            scale = 2 * float(camera["orthographicHalfHeight"]) / float(camera.get("zoom") or 1.0)
        cam.SetEyeAndCenter(gp_Pnt(*eye), gp_Pnt(*target))
        cam.SetUp(gp_Dir(*screen_up))
        if scale is not None:
            cam.SetScale(occt_scale(scale, aspect))
        self.canvas.view.ZFitAll(1.0)
        self.camera = {"fov": vertical_fov(aspect, focal_length), "direction": d, "up": screen_up, "right": right,
                       "eye": eye, "target": target, "projection": projection, "scale": scale}
        if self.studio:
            self._studio_backdrop()  # the sweep's shading follows the camera
        return self.camera

    def box_corners(self) -> np.ndarray:
        """The eight corners of the box of every part drawn, placed (``fitOrthographicCamera``'s fit)."""
        from cadgen.engine.render.explode import placed_box

        boxes = [placed_box(self.boxes[i["prototype"]], self.placement(n))
                 for n, i in enumerate(self.structure["instances"])
                 if i["prototype"] in self.boxes and n not in self.hidden]
        lo, hi = np.min([b[0] for b in boxes], 0), np.max([b[1] for b in boxes], 0)
        return np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])

    def frame(self, camera: str | dict[str, Any] = "iso", projection: str = "orthographic",
              focal_length: float = FOCAL_LENGTH, *, padding: float = PADDING, tight: bool = True) -> dict[str, Any]:
        """The snapshot page's framing: the direction a preset or ``az:el`` names, then the tight
        frame on every placed vertex (orthographic), or the perspective fit on the same points, with
        ``padding`` of the picture each side (a job's ``output.padding``); ``tight`` off (a job's
        ``output.tightFrame``) fits the drawn parts' box instead. Or a prompt view's own camera,
        placed as it is (``_pinned``)."""
        from OCP.gp import gp_Dir, gp_Pnt
        from OCP.Graphic3d import Graphic3d_Camera

        if isinstance(camera, dict):
            return self._pinned(camera, projection, focal_length)

        d, up = direction_of(camera)
        forward = -d
        right = np.cross(forward, up)
        right /= np.linalg.norm(right)
        screen_up = np.cross(right, forward)
        if not tight or (self.mode == "wireframe" and projection != "perspective"):
            # The page's tight frame fits the meshes it draws; Wireframe draws none, so the page
            # falls back to the scene's box (``fitOrthographicCamera``): its eight corners.
            points = self.box_corners()
        else:
            points = self.placed_points()
        width, height = self.canvas.width, self.canvas.height
        aspect = width / height
        safe = max(1 - 2 * padding, 0.1)
        low, high = points.min(0), points.max(0)
        centre = (low + high) / 2
        radius = float(np.linalg.norm(high - low)) / 2 or 1.0
        cam = self.canvas.view.Camera()
        cam.SetAspect(aspect)  # the picture's, so what projects through the camera lands where it is drawn
        if projection == "perspective":
            cam.SetProjectionType(Graphic3d_Camera.Projection_e.Projection_Perspective)
            fov = vertical_fov(aspect, focal_length)
            cam.SetFOVy(occt_fov(fov, aspect))
            vertical = math.tan(math.radians(fov / 2)) * safe
            horizontal = vertical * aspect
            relative = points - centre
            depth = relative @ d
            near = max(radius / 1200, 0.01) * 2
            distance = float(max(np.max(depth + np.abs(relative @ right) / horizontal),
                                 np.max(depth + np.abs(relative @ screen_up) / vertical), np.max(depth + near)))
            target, eye = centre, centre + d * distance
            scale = None
        else:
            cam.SetProjectionType(Graphic3d_Camera.Projection_e.Projection_Orthographic)
            xs, ys = points @ right, points @ screen_up
            half = max((ys.max() - ys.min()) / (2 * safe), (xs.max() - xs.min()) / (2 * aspect * safe), 1e-6)
            mid = right * (xs.max() + xs.min()) / 2 + screen_up * (ys.max() + ys.min()) / 2
            target = mid + d * float(centre @ d)
            eye = target + d * radius * 4
            scale = 2 * half
        cam.SetEyeAndCenter(gp_Pnt(*eye), gp_Pnt(*target))
        cam.SetUp(gp_Dir(*screen_up))
        if scale is not None:
            cam.SetScale(occt_scale(scale, aspect))
        self.canvas.view.ZFitAll(1.0)
        self.camera = {"fov": vertical_fov(aspect, focal_length), "direction": d, "up": screen_up, "right": right, "eye": eye, "target": target,
                       "projection": projection, "scale": scale}
        if self.studio:
            self._studio_backdrop()  # the sweep's shading follows the camera
        return self.camera

    def project(self, points: np.ndarray) -> np.ndarray:
        """World points to output pixels (x right, y down), through OCCT's own camera."""
        from OCP.gp import gp_Pnt

        cam = self.canvas.view.Camera()
        out = []
        for point in points:
            projected = cam.Project(gp_Pnt(*map(float, point)))  # normalized device coordinates
            out.append(((projected.X() + 1) / 2 * self.canvas.width, (1 - projected.Y()) / 2 * self.canvas.height))
        return np.array(out)

    # --- grid, explode, overlays -----------------------------------------------------------------

    def grid(self, on: bool = True) -> float:
        """The viewer's measuring grid for the camera framed (``grid.py``; after ``frame``), or none."""
        from cadgen.engine.render import grid

        return grid.show(self, on)

    def explode(self, amount: float) -> float:
        from cadgen.engine.render.explode import offsets

        clock = time.perf_counter()
        self.offsets = offsets(self.structure, [self.meshes[p["key"]] for p in self.prototypes], self.matrices,
                               amount) if amount > 0 else {}
        return time.perf_counter() - clock

    def clear_overlays(self, keep: Any = ()) -> None:
        """Every overlay gone but ``keep``'s (what is shown for good: Preview's floor)."""
        for shown in self.overlays:
            if not any(shown is kept for kept in keep):
                self.canvas.context.Remove(shown, False)
        self.overlays = [shown for shown in self.overlays if any(shown is kept for kept in keep)]
        for structure in self.structures:
            structure.Erase()
            structure.Remove()
        self.structures = []
        self.text_quads = []
        self.screen_marks = []
        self.fonts = set()

    def _pixel_size(self, point: np.ndarray) -> float:
        """World millimetres per output pixel at ``point`` for the camera framed."""
        camera = self.camera
        if camera["scale"] is not None:
            return camera["scale"] / self.canvas.height
        depth = float(np.dot(np.asarray(point) - camera["eye"], -camera["direction"]))
        return 2 * depth * math.tan(math.radians(camera["fov"] / 2)) / self.canvas.height

    def _ribbon(self, points: np.ndarray, color: str, width: float, closed: bool = False,
                widths: Any = None) -> None:
        """A polyline ``width`` pixels wide, as the viewer's screen-space lines are (three's
        ``Line2``): each segment its own quad facing the camera, as wide as the line at its two ends
        (``widths``: the pen's share of the width at each point), each point a disc of that width, so
        segments meet round however sharp the turn (a core-profile GL context draws GL lines one
        pixel wide)."""
        from OCP.AIS import AIS_Shape
        from OCP.Graphic3d import Graphic3d_TypeOfShadingModel, Graphic3d_ZLayerId_Top

        from cadgen.engine.render.shapes import craft, read

        points = np.asarray(points, float)
        shares = np.ones(len(points)) if widths is None or len(widths) != len(points) else np.asarray(widths, float)
        if closed:
            points, shares = np.vstack([points, points[:1]]), np.append(shares, shares[:1])
        view = np.asarray(self.camera["direction"], float)
        right, up = np.asarray(self.camera["right"], float), np.asarray(self.camera["up"], float)
        half = np.array([self._pixel_size(p) * width / 2 for p in points]) * shares
        steps = points[1:] - points[:-1]
        sides = np.cross(steps, view)
        sides /= np.maximum(np.linalg.norm(sides, axis=1, keepdims=True), 1e-12)
        count = len(steps)
        quads = np.empty((4 * count, 3))
        quads[0::4], quads[1::4] = points[:-1] + sides * half[:-1, None], points[:-1] - sides * half[:-1, None]
        quads[2::4], quads[3::4] = points[1:] + sides * half[1:, None], points[1:] - sides * half[1:, None]
        a = np.arange(count) * 4
        triangles = [np.stack([a, a + 1, a + 2], 1), np.stack([a + 1, a + 3, a + 2], 1)]
        rim = 16
        turn = np.linspace(0, 2 * math.pi, rim, endpoint=False)
        ring = np.cos(turn)[:, None] * right + np.sin(turn)[:, None] * up
        discs = (points[:, None, :] + ring[None] * half[:, None, None]).reshape(-1, 3)
        centres = len(quads) + len(discs) + np.arange(len(points))
        first = len(quads) + np.arange(len(points))[:, None] * rim
        k = np.arange(rim)[None, :]
        triangles.append(np.stack([np.repeat(centres, rim), (first + k).ravel(), (first + (k + 1) % rim).ravel()], 1))
        nodes = np.vstack([quads, discs, points])
        compound = read(craft([(nodes, np.concatenate(triangles), None)], {}))
        shown = AIS_Shape(compound)
        shown.SetColor(_color(color))
        aspect = shown.Attributes().ShadingAspect().Aspect()
        aspect.SetShadingModel(Graphic3d_TypeOfShadingModel.Graphic3d_TypeOfShadingModel_Unlit)
        self.canvas.context.Display(shown, 1, -1, False)
        self.canvas.context.SetZLayer(shown, Graphic3d_ZLayerId_Top)
        self.overlays.append(shown)

    def _polyline(self, points: np.ndarray, color: str, width: float, closed: bool = False,
                  widths: Any = None) -> None:
        if width > 1.5 and getattr(self, "camera", None) is not None:
            self._ribbon(points, color, width, closed, widths)
            return
        from OCP.AIS import AIS_Shape
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
        from OCP.Graphic3d import Graphic3d_ZLayerId_Top
        from OCP.gp import gp_Pnt

        polygon = BRepBuilderAPI_MakePolygon()
        for point in points:
            polygon.Add(gp_Pnt(*map(float, point)))
        if closed:
            polygon.Close()
        shown = AIS_Shape(polygon.Wire())
        shown.SetColor(_color(color))
        shown.SetWidth(width)
        self.canvas.context.Display(shown, 0, -1, False)
        self.canvas.context.SetZLayer(shown, Graphic3d_ZLayerId_Top)
        self.overlays.append(shown)

    def _text_quad(self, corners: np.ndarray, mark: dict[str, Any]) -> None:
        """A text mark as the viewer draws it (``annotation.js``): its words on the viewer's
        canvas (``text.text_canvas``) mapped onto the quad of its four corners -- corner 0 the
        canvas's top-left, 1 its top-right, 2 bottom-right, 3 bottom-left; triangles 0-1-2 and
        0-2-3 with three's uv (0,1) (1,1) (1,0) (0,0) -- unlit and two-sided, blended by the
        canvas's alpha, filtered trilinearly from mipmaps; drawn after the model in the Top layer,
        so hidden where the model is in front of it, and writing no depth, as the viewer's mesh
        (``depthTest``, no ``depthWrite``, render order 40)."""
        from OCP.Aspect import Aspect_InteriorStyle
        from OCP.Graphic3d import (Graphic3d_AlphaMode, Graphic3d_ArrayOfTriangles, Graphic3d_AspectFillArea3d,
                                   Graphic3d_Group, Graphic3d_LevelOfTextureAnisotropy, Graphic3d_Structure,
                                   Graphic3d_Texture2D, Graphic3d_TypeOfBackfacingModel, Graphic3d_TypeOfShadingModel,
                                   Graphic3d_TypeOfTextureFilter, Graphic3d_ZLayerId_Top)
        from OCP.Image import Image_Format, Image_PixMap
        from OCP.Quantity import Quantity_Color, Quantity_ColorRGBA, Quantity_TOC_RGB
        from OCP.gp import gp_Pnt, gp_Pnt2d

        from cadgen.engine.render.text import TEXT_SCALE, face, text_canvas

        picture = text_canvas(mark.get("text", ""), float(mark.get("fontPx", 14)), mark["color"])
        self.fonts.add(face(500, float(mark.get("fontPx", 14)) * TEXT_SCALE).name)
        height, width = picture.shape[:2]
        pixmap = Image_PixMap()
        pixmap.InitZero(Image_Format.Image_Format_RGBA, width, height)
        ys, xs = np.nonzero(picture[..., 3])
        # The canvas's bytes as they are (sRGB colour, straight alpha): OCCT reads a colour
        # texture's bytes as sRGB, as three reads a canvas texture marked SRGBColorSpace.
        for x, y, (r, g, b, a) in zip(xs.tolist(), ys.tolist(), (picture[ys, xs] / 255.0).tolist()):
            pixmap.SetPixelColor(x, y, Quantity_ColorRGBA(r, g, b, a), False)
        texture = Graphic3d_Texture2D(pixmap)
        params = texture.GetParams()
        params.SetFilter(Graphic3d_TypeOfTextureFilter.Graphic3d_TOTF_TRILINEAR)
        params.SetAnisoFilter(Graphic3d_LevelOfTextureAnisotropy.Graphic3d_LOTA_OFF)
        params.SetRepeat(False)
        params.SetModulate(True)
        texture.SetMipmapsGeneration(True)
        triangles = Graphic3d_ArrayOfTriangles(4, 6, False, False, True)
        for point, (u, v) in zip(corners, ((0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0))):
            triangles.AddVertex(gp_Pnt(*map(float, point)), gp_Pnt2d(u, v))
        triangles.AddEdges(1, 2, 3)
        triangles.AddEdges(1, 3, 4)
        aspect = Graphic3d_AspectFillArea3d()
        aspect.SetInteriorStyle(Aspect_InteriorStyle.Aspect_IS_SOLID)
        aspect.SetShadingModel(Graphic3d_TypeOfShadingModel.Graphic3d_TypeOfShadingModel_Unlit)
        aspect.SetInteriorColor(Quantity_ColorRGBA(Quantity_Color(1, 1, 1, Quantity_TOC_RGB), 1.0))
        aspect.SetAlphaMode(Graphic3d_AlphaMode.Graphic3d_AlphaMode_Blend, 0.5)
        aspect.SetFaceCulling(Graphic3d_TypeOfBackfacingModel.Graphic3d_TypeOfBackfacingModel_DoubleSided)
        aspect.SetTextureMap(texture)
        aspect.SetTextureMapOn(True)
        structure = Graphic3d_Structure(self.canvas.viewer.StructureManager())
        group = structure.NewGroup()
        group.SetGroupPrimitivesAspect(aspect)
        Graphic3d_Group.AddPrimitiveArray(group, triangles)
        structure.SetZLayer(Graphic3d_ZLayerId_Top)
        structure.Display()
        self.structures.append(structure)
        self.text_quads.append((np.asarray(corners, float), mark["color"]))

    def annotate(self, annotation: dict[str, Any]) -> list[np.ndarray]:
        """The viewer's annotation data drawn: each mark's points in its part's frame (``part``:
        ``i<instance>``, placed where the scene now has the instance; else its recorded placement),
        a stroke a polyline of its width, a text mark its words on its quad (``_text_quad``). The
        points and the recorded placements are in the viewer's scene coordinates, as it wrote them
        (``millimetres_per_scene_unit`` of the scene's millimetres each). Returns each mark's world
        points, for checking where they land."""
        scale = self.canvas.height / REFERENCE_HEIGHT
        factor = self.millimetres_per_scene_unit
        placed_marks = []
        for mark in annotation.get("marks", []):
            points = np.array(mark["points"], float).reshape(-1, 3) * factor
            part = mark.get("part")
            if part and part.startswith("i") and part[1:].isdigit() and int(part[1:]) < len(self.matrices):
                matrix = self.placement(int(part[1:]))
            elif part and part in annotation.get("parts", {}):
                matrix = _matrix(annotation["parts"][part]["placement"])
                matrix[:3, 3] *= factor  # the viewer's placement: its translation in its coordinates
            else:
                matrix = np.eye(4)
            world = points @ matrix[:3, :3].T + matrix[:3, 3]
            placed_marks.append(world)
            if mark["kind"] == "stroke":
                self._polyline(world, mark["color"], mark.get("width", 2) * scale, bool(mark.get("closed")), mark.get("widths"))
            elif mark["kind"] == "area":
                self._polyline(world[:mark.get("outline", len(world))], mark["color"], 1.5 * scale, True)
            elif len(world) == 4:
                self._text_quad(world, mark)
        return placed_marks

    def measure(self, marks: list[dict[str, Any]]) -> None:
        """The snapshot job's ``measurements``, painted over the finished frame as the snapshot
        page paints them on its 2D canvas (``overlay.py``): in screen space, over everything. Their
        ``start`` and ``end`` are in the viewer's scene coordinates, as Measure took them
        (``millimetres_per_scene_unit`` of the scene's millimetres each)."""
        from cadgen.engine.render.overlay import LABEL_FACE
        from cadgen.engine.render.text import face

        factor = self.millimetres_per_scene_unit
        self.screen_marks = [{**mark, "start": [float(value) * factor for value in mark["start"]],
                              "end": [float(value) * factor for value in mark["end"]]} for mark in marks]
        if any(str(mark.get("label") or "").strip() for mark in marks):
            self.fonts.add(face(*LABEL_FACE).name)

    # --- preview ------------------------------------------------------------------------------

    def _structure(self, triangles: Any, aspect: Any, priority: Any) -> Any:
        """A presentation below AIS (``Graphic3d_Structure``) of ``triangles`` in ``aspect``, in the
        default layer, infinite to the view (no fit, no shadow frame takes it), never cut by Clip
        (the viewer's studio is whole whatever its Clip cuts)."""
        from OCP.Graphic3d import Graphic3d_Group, Graphic3d_Structure

        from cadgen.engine.render.grid import unclipped

        structure = Graphic3d_Structure(self.canvas.viewer.StructureManager())
        group = structure.NewGroup()
        group.SetGroupPrimitivesAspect(aspect)
        Graphic3d_Group.AddPrimitiveArray(group, triangles)
        structure.SetClipPlanes(unclipped())
        structure.SetInfiniteState(True)
        structure.SetDisplayPriority(priority)
        structure.Display()
        self.stage.append(structure)
        return structure

    @staticmethod
    def _unlit(texture: Any = None) -> Any:
        """An unlit, two-sided, alpha-blended look (by vertex colour, or by ``texture``)."""
        from OCP.Aspect import Aspect_InteriorStyle
        from OCP.Graphic3d import (Graphic3d_AlphaMode, Graphic3d_AspectFillArea3d, Graphic3d_TypeOfBackfacingModel,
                                   Graphic3d_TypeOfShadingModel)
        from OCP.Quantity import Quantity_Color, Quantity_ColorRGBA, Quantity_TOC_RGB

        aspect = Graphic3d_AspectFillArea3d()
        aspect.SetInteriorStyle(Aspect_InteriorStyle.Aspect_IS_SOLID)
        aspect.SetShadingModel(Graphic3d_TypeOfShadingModel.Graphic3d_TypeOfShadingModel_Unlit)
        aspect.SetInteriorColor(Quantity_ColorRGBA(Quantity_Color(1, 1, 1, Quantity_TOC_RGB), 1.0))
        aspect.SetAlphaMode(Graphic3d_AlphaMode.Graphic3d_AlphaMode_Blend, 0.5)
        aspect.SetFaceCulling(Graphic3d_TypeOfBackfacingModel.Graphic3d_TypeOfBackfacingModel_DoubleSided)
        if texture is not None:
            aspect.SetTextureMap(texture)
            aspect.SetTextureMapOn(True)
        return aspect

    @staticmethod
    def _texture(picture: np.ndarray, *, smooth: bool = True) -> Any:
        """``picture`` (rows top first, RGB or RGBA bytes, sRGB) as an OCCT texture, filtered."""
        from OCP.Graphic3d import Graphic3d_Texture2D, Graphic3d_TypeOfTextureFilter
        from OCP.Image import Image_Format, Image_PixMap
        from OCP.Quantity import Quantity_ColorRGBA

        height, width, depth = picture.shape
        pixmap = Image_PixMap()
        pixmap.InitZero(Image_Format.Image_Format_RGBA if depth == 4 else Image_Format.Image_Format_RGB, width, height)
        values = picture.astype(np.float64) / 255.0
        if depth == 4:
            ys, xs = np.nonzero(picture[..., 3])
        else:
            ys, xs = np.nonzero(np.ones((height, width), bool))
        for x, y, value in zip(xs.tolist(), ys.tolist(), values[ys, xs].tolist()):
            pixmap.SetPixelColor(x, y, Quantity_ColorRGBA(value[0], value[1], value[2], value[3] if depth == 4 else 1.0), False)
        texture = Graphic3d_Texture2D(pixmap)
        params = texture.GetParams()
        params.SetFilter(Graphic3d_TypeOfTextureFilter.Graphic3d_TOTF_BILINEAR if smooth
                         else Graphic3d_TypeOfTextureFilter.Graphic3d_TOTF_NEAREST)
        params.SetRepeat(False)
        params.SetModulate(True)
        return texture

    def backdrop(self, colour: Any = None) -> None:
        """What is behind the model, for a picture matted on nothing (``service.matte``): ``colour``
        (an RGB triple, 0 to 1) flat, or -- None -- the look's own again: Preview's studio sweep,
        else the look's backdrop."""
        from OCP.Aspect import Aspect_FillMethod, Aspect_GradientFillMethod

        vertical = Aspect_GradientFillMethod.Aspect_GradientFillMethod_Vertical
        if colour is None:
            if self.studio:
                self._studio_backdrop()
            else:
                self.canvas.view.SetBgGradientColors(_color(BACKGROUND), _color(BACKGROUND), vertical, False)
            return
        if self.studio:
            picture = np.broadcast_to(np.rint(np.asarray(colour, float) * 255).astype(np.uint8), (2, 2, 3))
            graphic = self.canvas.view.View()
            graphic.SetBackgroundImage(self._texture(np.ascontiguousarray(picture), smooth=False), False)
            graphic.SetBackgroundImageStyle(Aspect_FillMethod.Aspect_FM_STRETCH)
        else:
            self.canvas.view.SetBgGradientColors(_color(tuple(colour)), _color(tuple(colour)), vertical, False)

    def _studio_backdrop(self) -> None:
        """The viewer's backdrop (``studioBackdrop.js``) behind everything, for the camera framed:
        its colour lifted toward white behind the middle of the frame (a little above it), shaded
        toward the corners and, above the horizon, by how far the view looks up. Drawn as a picture
        stretched over the view, in display colour, as the viewer draws it into its canvas."""
        from OCP.Aspect import Aspect_FillMethod

        camera = self.camera
        width, height = 96, 72
        aspect = self.canvas.width / self.canvas.height
        ys, xs = np.mgrid[0:height, 0:width]
        nx, ny = (xs + 0.5) / width * 2 - 1, 1 - (ys + 0.5) / height * 2

        def smoothstep(low: float, high: float, value: np.ndarray) -> np.ndarray:
            t = np.clip((value - low) / (high - low), 0, 1)
            return t * t * (3 - 2 * t)

        forward = -np.asarray(camera["direction"], float)
        if camera["projection"] == "perspective":
            tangent = math.tan(math.radians(camera["fov"]) / 2)
            rays = (forward[None, None, :] + (nx * tangent * aspect)[..., None] * camera["right"]
                    + (ny * tangent)[..., None] * camera["up"])
        else:
            rays = np.broadcast_to(forward, (height, width, 3))
        rays = rays / np.linalg.norm(rays, axis=-1, keepdims=True)
        reach = np.clip(np.hypot(nx * aspect, ny - 0.12) / math.hypot(aspect, 1.12), 0, 1)
        glow = 1 - smoothstep(0.0, 0.75, reach)
        corner = smoothstep(0.3, 1.0, reach)
        wall = smoothstep(0.0, 0.55, rays[..., 2])
        base = np.array([int(BACKDROP[i:i + 2], 16) for i in (1, 3, 5)], float) / 255
        luma = float(base @ [0.2126, 0.7152, 0.0722])
        shade = BACKDROP_SHADE[0] + (BACKDROP_SHADE[1] - BACKDROP_SHADE[0]) * luma
        colour = base + (1 - base) * (BACKDROP_LIFT * glow * glow)[..., None]
        colour = colour * (1 - shade * np.clip(corner + BACKDROP_WALL * wall, 0, 1))[..., None]
        picture = np.rint(np.clip(colour, 0, 1) * 255).astype(np.uint8)
        # Shown behind the model, not lighting it: the image-based light stays the one baked from
        # the environment's cube map (V3d_View.SetBackgroundImage would bake it again from this).
        graphic = self.canvas.view.View()
        graphic.SetBackgroundImage(self._texture(picture), False)
        graphic.SetBackgroundImageStyle(Aspect_FillMethod.Aspect_FM_STRETCH)

    def _studio_place(self) -> dict[str, Any]:
        """Where the viewer's studio puts its floor and its shadow (``updateGround``): the floor at
        the model's lowest point as it stands (Preview's default placement, core's
        ``RENDER_FLOOR_PLACEMENT``), centred under the model at rest, its reach the larger of the
        model's radius and its footprint's half-diagonal; the shadow's square ``reach`` of the
        model's height past its footprint, occlusion reaching ``height`` of that height above the
        floor."""
        from cadgen.engine.render.explode import placed_box

        low, high = self.rest_bounds()
        span = high - low
        radius = float(np.linalg.norm(span)) / 2 or 1.0
        # The lowest point of the parts' boxes where they stand now, as the viewer's scene measures
        # its bounds (three's ``Box3.applyMatrix4``, ``placed_box``): a pose or Explode moves it.
        floor = float(min(placed_box(self.boxes[i["prototype"]], self.placement(n))[0][2]
                          for n, i in enumerate(self.structure["instances"]) if i["prototype"] in self.boxes))
        above = max(float(high[2]) - floor, radius * 0.05)
        half_span = float(max(span[0], span[1])) / 2
        return {"centre": ((low[0] + high[0]) / 2, (low[1] + high[1]) / 2), "z": floor, "radius": radius,
                "reach": max(radius, math.hypot(span[0], span[1]) / 2),
                "shadow_half": (half_span + above * CONTACT_REACH) * 1.12,
                "range": max(above, half_span * 0.5) * CONTACT_HEIGHT, "top": float(high[2])}

    def _studio_floor(self, place: dict[str, Any]) -> None:
        """The viewer's floor: #e7e7e5 at 60%, as its Preview draws it (``FLOOR_COLOUR``), unlit,
        full out to ``FLOOR_FADE[0]`` of the model's reach and fading (squared, a long tail) to
        nothing at ``FLOOR_FADE[1]`` of it, so it has no edge from any camera: a disc of rings, the
        fade in its vertices' alpha."""
        from OCP.Graphic3d import Graphic3d_ArrayOfTriangles, Graphic3d_DisplayPriority
        from OCP.collections import Vec4_uint8_t
        from OCP.gp import gp_Pnt

        rings, segments = 48, 96
        outer = place["reach"] * FLOOR_FADE[1]
        cx, cy = place["centre"]
        rgb = [int(FLOOR_COLOUR[i:i + 2], 16) for i in (1, 3, 5)]
        triangles = Graphic3d_ArrayOfTriangles(1 + rings * segments, 3 * segments * (2 * rings - 1), False, True, False)
        angles = np.linspace(0, 2 * math.pi, segments, endpoint=False)
        for ring in range(rings + 1):
            fraction = ring / rings
            t = np.clip((fraction - FLOOR_FADE[0] / FLOOR_FADE[1]) / (1 - FLOOR_FADE[0] / FLOOR_FADE[1]), 0, 1)
            fade = (1 - t * t * (3 - 2 * t)) ** 2
            colour = Vec4_uint8_t(*rgb, int(round(255 * FLOOR_OPACITY * fade)))
            if ring == 0:
                triangles.AddVertex(gp_Pnt(cx, cy, place["z"]), colour)
                continue
            for angle in angles:
                r = outer * fraction
                triangles.AddVertex(gp_Pnt(cx + r * math.cos(angle), cy + r * math.sin(angle), place["z"]), colour)
        for segment in range(segments):  # 1-based: the centre is 1, ring k's s-th point 2 + (k-1)*segments + s
            following = (segment + 1) % segments
            triangles.AddEdges(1, 2 + segment, 2 + following)
            for ring in range(1, rings):
                inner, outer_ring = 2 + (ring - 1) * segments, 2 + ring * segments
                triangles.AddEdges(inner + segment, outer_ring + segment, outer_ring + following)
                triangles.AddEdges(inner + segment, outer_ring + following, inner + following)
        self._structure(triangles, self._unlit(), Graphic3d_DisplayPriority.Graphic3d_DisplayPriority_Below)

    def _depth(self, eye: Any, target: Any, up: Any, scale: float, size: int, z_range: Any = None,
               keep_above: float | None = None) -> np.ndarray:
        """The model's depth (0 near to 1 far; 1 where nothing is) from an orthographic camera, as
        floats (rows top first): OCCT dumps a depth picture to bytes stretched over its own range,
        so its two ends are read back as floats and the bytes put back between them. The camera,
        its depth fit, the clip planes, multisampling and the shadow map are put back after."""
        from OCP.Graphic3d import (Graphic3d_BufferType, Graphic3d_Camera, Graphic3d_ClipPlane,
                                   Graphic3d_ZLayerId_Default)
        from OCP.Image import Image_AlienPixMap
        from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

        from cadgen.engine.render.context import pixels

        view = self.canvas.view
        camera = view.Camera()
        kept = Graphic3d_Camera(camera)
        params = view.ChangeRenderingParams()
        shadows, msaa = params.IsShadowEnabled, params.NbMsaaSamples
        auto = view.AutoZFitMode()
        clip = None
        try:
            params.IsShadowEnabled = False
            params.NbMsaaSamples = 0
            camera.SetProjectionType(Graphic3d_Camera.Projection_e.Projection_Orthographic)
            camera.SetEyeAndCenter(gp_Pnt(*map(float, eye)), gp_Pnt(*map(float, target)))
            camera.SetUp(gp_Dir(*map(float, up)))
            camera.SetScale(float(scale))
            if z_range is not None:
                view.SetAutoZFitMode(False)
                camera.SetZRange(float(z_range[0]), float(z_range[1]))
            if keep_above is not None:
                clip = Graphic3d_ClipPlane(gp_Pln(gp_Pnt(0, 0, float(keep_above)), gp_Dir(0, 0, 1)))
                view.AddClipPlane(clip)
            image = Image_AlienPixMap()
            # Up to the default layer: the overlay layers above it clear the depth they draw over.
            if not view.ToPixMap(image, size, size, Graphic3d_BufferType.Graphic3d_BT_Depth, False,
                                 Graphic3d_ZLayerId_Default, 0):
                raise RuntimeError("OCCT drew no depth")
            levels = pixels(image)[..., 0].astype(np.float64)
            low_at, high_at = np.unravel_index(levels.argmin(), levels.shape), np.unravel_index(levels.argmax(), levels.shape)
            low = image.PixelColor(int(low_at[1]), int(low_at[0])).GetRGB().Red()
            high = image.PixelColor(int(high_at[1]), int(high_at[0])).GetRGB().Red()
            return low + levels / 255.0 * (high - low)
        finally:
            if clip is not None:
                view.RemoveClipPlane(clip)
            view.SetAutoZFitMode(auto)
            camera.Copy(kept)
            params.IsShadowEnabled, params.NbMsaaSamples = shadows, msaa

    def _contact_shadow(self, place: dict[str, Any]) -> None:
        """The viewer's floor shadow (``studioContactShadow.js``), baked as it bakes it: the
        heights of the lowest surfaces over the floor, seen from just below it (contact: tight, and
        occlusion: broad, both 1 at the floor and 0 at the top of the contact range), and whether
        the viewer's key reaches each floor point (its direction, ``KEY_DIRECTION``; the model above
        the floor seen along it), each blurred as it blurs them (narrow, medium, wide), put together
        as it does (the key's shadow crisp and full near the model, soft and light away from it), and
        faded inside the square. Laid on the floor as an unlit black picture of that darkness at
        the floor's opacity, its alpha set so OCCT's blend in linear light leaves what three's blend
        of display colours leaves on the floor."""
        from OCP.Graphic3d import Graphic3d_ArrayOfTriangles, Graphic3d_DisplayPriority
        from OCP.gp import gp_Pnt, gp_Pnt2d

        size = SHADOW_TEXELS
        cx, cy = place["centre"]
        half, contact, floor = place["shadow_half"], place["range"], place["z"]
        below = contact * 0.004
        # Heights, from just below the floor looking up: the camera's right is -x (columns mirrored).
        depth = self._depth((cx, cy, floor - below), (cx, cy, floor + contact), (0, 1, 0), 2 * half, size,
                            z_range=(below * 0.5, below + contact))[:, ::-1]
        height = below * 0.5 + depth * (below + contact - below * 0.5) - below
        near = 1 - np.clip(height / contact, 0, 1)
        # The key: the model above the floor, seen along the key's direction.
        light = np.asarray(KEY_DIRECTION, float) / np.linalg.norm(KEY_DIRECTION)
        right = np.cross(-light, (0, 0, 1))
        right /= np.linalg.norm(right)
        up = np.cross(right, -light)
        origin = np.array([cx, cy, floor])
        low, high = self.rest_bounds()
        corners = [np.array([x, y, z]) for x in (low[0], high[0], cx - half, cx + half) for y in (low[1], high[1], cy - half, cy + half)
                   for z in (floor, high[2])]
        reach = 1.02 * max(max(abs((c - origin) @ right), abs((c - origin) @ up)) for c in corners)
        seen = self._depth(origin + light * place["radius"] * 10, origin, up, 2 * reach, size, keep_above=floor) < 0.999999
        texel = (np.arange(size) + 0.5) / size * 2 - 1
        xs, ys = cx + texel[None, :] * half, cy - texel[:, None] * half  # rows top first: +y at the top
        u = ((xs - cx) * right[0] + (ys - cy) * right[1]) / reach
        v = ((xs - cx) * up[0] + (ys - cy) * up[1]) / reach
        columns = np.clip((u + 1) / 2 * size - 0.5, 0, size - 1)
        rows = np.clip((1 - v) / 2 * size - 0.5, 0, size - 1)
        c0, r0 = np.floor(columns).astype(int), np.floor(rows).astype(int)
        c1, r1 = np.minimum(c0 + 1, size - 1), np.minimum(r0 + 1, size - 1)
        fc, fr = columns - c0, rows - r0
        mask = seen.astype(np.float64)
        blocked = ((mask[r0, c0] * (1 - fc) + mask[r0, c1] * fc) * (1 - fr) + (mask[r1, c0] * (1 - fc) + mask[r1, c1] * fc) * fr)

        def blur(picture: np.ndarray, share: float) -> np.ndarray:
            sigma = share * size
            taps = np.arange(-math.ceil(2 * sigma), math.ceil(2 * sigma) + 1)
            kernel = np.exp(-0.5 * (taps / sigma) ** 2)
            kernel /= kernel.sum()
            pad = len(taps) // 2
            for axis in (0, 1):
                padded = np.pad(picture, [(pad, pad) if a == axis else (0, 0) for a in (0, 1)], mode="edge")
                picture = np.apply_along_axis(lambda line: np.convolve(line, kernel, mode="valid"), axis, padded)
            return picture

        narrow, medium, wide = CONTACT_BLUR
        r, g = blur(near ** 3, narrow), blur(near, wide)
        b, a = blur(blocked, narrow), blur(blocked, medium)
        strength = CONTACT_STRENGTH
        occlusion = 1 - (1 - strength[0] * r) * (1 - strength[1] * g)
        t = np.clip(g / 0.5, 0, 1)
        proximity = t * t * (3 - 2 * t)
        key = (a + (b - a) * proximity) * (strength[3] + (strength[2] - strength[3]) * proximity)
        darkness = 1 - (1 - occlusion) * (1 - key)
        uv = (np.arange(size) + 0.5) / size
        edge = np.minimum(np.minimum(uv, 1 - uv)[None, :], np.minimum(uv, 1 - uv)[:, None])
        t = np.clip(edge / 0.08, 0, 1)
        alpha = darkness * t * t * (3 - 2 * t) * FLOOR_OPACITY
        # Black over the floor: three leaves (1 - alpha) of the floor's display colour, OCCT the
        # same share of its light; so OCCT's alpha is what leaves that display colour.
        under = np.array([int(FLOOR_COLOUR[i:i + 2], 16) for i in (1, 3, 5)], float) / 255 * FLOOR_OPACITY + (1 - FLOOR_OPACITY)
        lum = float(under @ [0.2126, 0.7152, 0.0722])

        def linear(c: Any) -> Any:
            return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

        alpha = 1 - linear((1 - alpha) * lum) / linear(lum)
        picture = np.zeros((size, size, 4), np.uint8)
        picture[..., 3] = np.rint(np.clip(alpha, 0, 1) * 255).astype(np.uint8)
        quad = Graphic3d_ArrayOfTriangles(4, 6, False, False, True)
        lift = floor + place["radius"] * 1e-4
        for x, y, uvx, uvy in ((cx - half, cy - half, 0, 0), (cx + half, cy - half, 1, 0), (cx + half, cy + half, 1, 1),
                               (cx - half, cy + half, 0, 1)):
            quad.AddVertex(gp_Pnt(x, y, lift), gp_Pnt2d(uvx, uvy))
        quad.AddEdges(1, 2, 3)
        quad.AddEdges(1, 3, 4)
        self._structure(quad, self._unlit(self._texture(picture)), Graphic3d_DisplayPriority.Graphic3d_DisplayPriority_Normal)

    def _studio(self) -> None:
        """The viewer's Preview studio around the model: its floor and the floor's shadow (its
        backdrop, ``_studio_backdrop``, goes behind once the environment that lights the model,
        ``_studio_environment``'s and unchanged, is baked)."""
        self.clear_stage()
        place = self._studio_place()
        self._contact_shadow(place)  # baked from the model alone, before the floor exists
        self._studio_floor(place)
        self.staged = self._placed()

    def _placed(self) -> bytes:
        shown = [i for i in range(len(self.matrices)) if i not in self.hidden]  # a part hidden is no shadow
        return np.round(np.concatenate([self.placement(i).ravel() for i in shown] or [np.zeros(1)]), 6).tobytes()

    def restage(self) -> None:
        """Preview's floor shadow baked again when the parts moved since it was (a pose, Explode),
        as the viewer bakes it again: the floor and the shadow's square stay where the model at rest
        put them."""
        if self.studio and self._placed() != self.staged:
            self._studio()

    def clear_stage(self) -> None:
        for structure in self.stage:
            structure.Erase()
            structure.Remove()
        self.stage = []

    def preview_look(self, path_trace: int = 0) -> float:
        """Preview's photographic look: PBR raster under an image-based environment and a key
        light, in the viewer's studio (``_studio``): its white sweep behind, its floor fading into
        it, the floor's soft shadow baked as the viewer bakes it; or OCCT's path tracer."""
        from OCP.Graphic3d import (Graphic3d_BSDF, Graphic3d_RenderingMode, Graphic3d_ToneMappingMethod,
                                   Graphic3d_TypeOfShadingModel)
        from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
        from OCP.V3d import V3d_AmbientLight, V3d_DirectionalLight
        from OCP.gp import gp_Dir

        clock = time.perf_counter()
        viewer, view = self.canvas.viewer, self.canvas.view
        for light in self.lights:
            viewer.DelLight(light)
        self.lights = []
        key = V3d_DirectionalLight(gp_Dir(0.5, 0.7, -1.0), Quantity_Color(1, 0.97, 0.92, Quantity_TOC_RGB))
        key.SetIntensity(2.5)
        key.SetCastShadows(True)
        key.SetHeadlight(False)
        ambient = V3d_AmbientLight(Quantity_Color(1, 1, 1, Quantity_TOC_RGB))
        ambient.SetIntensity(float(os.environ.get("OCCT_PBR_AMB", 1.0)))
        viewer.AddLight(key)
        viewer.SetLightOn(key)
        viewer.AddLight(ambient)
        viewer.SetLightOn(ambient)
        self.lights = [key, ambient]
        view.SetBackgroundColor(_color((0.93, 0.93, 0.94)))
        view.SetShadingModel(Graphic3d_TypeOfShadingModel.Graphic3d_TypeOfShadingModel_Pbr)
        params = view.ChangeRenderingParams()
        params.ToneMappingMethod = Graphic3d_ToneMappingMethod.Graphic3d_ToneMappingMethod_Filmic
        params.WhitePoint = 1.0
        # The key's shadow map shades the model only: the floor is unlit, its shadow the baked one.
        params.IsShadowEnabled = True
        params.ShadowMapResolution = 4096
        params.ShadowMapBias = 0.002
        self._studio()
        if path_trace:
            from cadgen.engine.render import clip as section

            section.withdraw(self)
            for source in self.sources.values():
                aspect = source.Attributes().ShadingAspect()
                face = aspect.Material()
                face.SetBSDF(Graphic3d_BSDF.CreateMetallicRoughness_s(face.PBRMaterial()))
                aspect.SetMaterial(face)
                source.SynchronizeAspects()
            params.Method = Graphic3d_RenderingMode.Graphic3d_RM_RAYTRACING
            params.IsGlobalIlluminationEnabled = True
            params.RaytracingDepth = 8
            params.IsAntialiasingEnabled = True
            params.CoherentPathTracingMode = False
            params.AdaptiveScreenSampling = False
            params.RadianceClampingValue = 30.0
            params.TwoSidedBsdfModels = True
            params.NbMsaaSamples = 0
            self._studio_backdrop()
        else:
            from OCP.Graphic3d import Graphic3d_CubeMapPacked

            cubemap = Graphic3d_CubeMapPacked(_studio_environment())
            cubemap.SetMipmapsGeneration(True)
            view.SetBackgroundCubeMap(cubemap, True, False)
            view.SetImageBasedLighting(True)
            view.Redraw()  # bakes the environment's lighting from the cube map
            params.PbrEnvPow2Size = 9
            params.PbrEnvSpecMapNbLevels = 8
            self._studio_backdrop()  # in place of the cube map, which only lights
        self.studio = True
        return time.perf_counter() - clock

    def path_trace(self, out: Path, samples: int) -> float:
        """Accumulate ``samples`` path-traced frames in the view's own frame buffer and write it:
        ``ToPixMap`` would make a new buffer and start the accumulation over."""
        from OCP.Graphic3d import Graphic3d_BufferType
        from OCP.Image import Image_AlienPixMap, Image_Format
        from OCP.TCollection import TCollection_AsciiString

        clock = time.perf_counter()
        width, height = self.canvas.width, self.canvas.height
        graphic = self.canvas.view.View()
        graphic.SetFBO(graphic.FBOCreate(width, height))
        for _ in range(samples):
            self.canvas.view.Redraw()
        image = Image_AlienPixMap()
        image.InitZero(Image_Format.Image_Format_RGB, width, height)
        graphic.BufferDump(image, Graphic3d_BufferType.Graphic3d_BT_RGB)
        image.Save(TCollection_AsciiString(str(out)))
        return time.perf_counter() - clock

    def _relay_text(self, frame: np.ndarray) -> None:
        """The text marks laid over ``frame`` as three lays them. OCCT blends a transparent quad
        in linear light (its frame buffer is sRGB); three blends the sRGB values themselves (it
        encodes in the shader and draws into a plain 8-bit buffer), which leaves a glyph's partly
        covered pixels darker. So each quad's rectangle of the frame is drawn again without the
        quads (a camera tile, ``Canvas.tile``), the quad's coverage as drawn (filtered, hidden
        behind the model) is read back from the two in linear light, and the mark's colour is laid
        over the bare pixels by that coverage, in sRGB."""
        height, width = frame.shape[:2]
        boxes = []
        for corners, color in self.text_quads:
            screen = self.project(corners)
            x0, y0 = (int(max(math.floor(v) - 2, 0)) for v in screen.min(0))
            x1, y1 = int(min(math.ceil(screen[:, 0].max()) + 3, width)), int(min(math.ceil(screen[:, 1].max()) + 3, height))
            if x1 > x0 and y1 > y0:
                boxes.append((x0, y0, x1, y1, color))
        if not boxes:
            return
        for structure in self.structures:
            structure.Erase()
        try:
            bares = [self.canvas.tile(x0, y0, x1 - x0, y1 - y0) for x0, y0, x1, y1, _color in boxes]
        finally:
            for structure in self.structures:
                structure.Display()

        def linear(c: np.ndarray) -> np.ndarray:
            return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)

        for (x0, y0, x1, y1, color), bare in zip(boxes, bares):
            drawn = frame[y0:y1, x0:x1]
            touched = (drawn != bare).any(-1)
            if not touched.any():
                continue
            ink = np.array([int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], float) / 255
            seen, under = drawn[touched].astype(np.float64) / 255, bare[touched].astype(np.float64) / 255
            span = linear(ink) - linear(under)
            weight = np.where(np.abs(span) > 0.02, np.abs(span), 0.0)
            ratio = (linear(seen) - linear(under)) / np.where(weight > 0, span, 1.0)
            cover = np.clip((ratio * weight).sum(-1) / np.maximum(weight.sum(-1), 1e-9), 0, 1)[:, None]
            drawn[touched] = np.rint((ink * cover + under * (1 - cover)) * 255).astype(np.uint8)

    def painter(self) -> Any:
        """What paints over the finished frame (sRGB bytes, in place): the text marks as three lays
        them, then Measure's marks; None when there is nothing to paint."""
        if not (self.text_quads or self.screen_marks):
            return None

        def paint(frame: np.ndarray) -> None:
            if self.text_quads:
                self._relay_text(frame)
            if self.screen_marks:
                from cadgen.engine.render.overlay import paint_measurements

                paint_measurements(frame, self.screen_marks, self.project)
        return paint

    def save(self, out: Path) -> float:
        return self.canvas.save(str(out), self.painter())


_ENVIRONMENT = None


def _studio_environment(size: int = 64) -> Any:
    """A soft studio as a packed cube map (+X, -X, +Y, -Y, +Z, -Z), made in memory: a bright
    sky over a grey horizon and a dark floor, with three soft boxes. OCCT reads no HDR file here."""
    global _ENVIRONMENT
    if _ENVIRONMENT is not None:
        return _ENVIRONMENT
    from OCP.Image import Image_Format, Image_PixMap
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB

    a = (np.arange(size) + 0.5) / size * 2 - 1
    s, t = np.meshgrid(a, a)
    one = np.ones_like(s)
    faces = [(one, -t, -s), (-one, -t, s), (s, one, t), (s, -one, -t), (s, -t, one), (-s, -t, -one)]
    strips = []
    for face in faces:
        v = np.stack(face, -1)
        v /= np.linalg.norm(v, axis=-1, keepdims=True)
        z = v[..., 2]
        sky, horizon, floor = np.array([0.92, 0.94, 0.97]), np.array(HORIZON), np.array([0.25, 0.25, 0.26])
        w = np.clip(z, 0, 1)[..., None] ** 0.6
        c = np.where(z[..., None] > 0, horizon * (1 - w) + sky * w,
                     horizon * np.clip(1 + z * 4, 0, 1)[..., None] + floor * np.clip(-z * 4, 0, 1)[..., None])
        for direction, spread, gain in (((-0.6, -0.8, 0.7), 0.30, 1.0), ((0.9, 0.6, 0.4), 0.18, 0.6), ((0, 0, 1), 0.25, 0.4)):
            dd = np.array(direction) / np.linalg.norm(direction)
            c = c + (np.clip((v @ dd - math.cos(spread)) / 0.02, 0, 1) * gain)[..., None]
        strips.append(np.clip(c, 0, 1))
    array = np.concatenate(strips, axis=1)
    height, width = array.shape[:2]
    pixmap = Image_PixMap()
    pixmap.InitTrash(Image_Format.Image_Format_RGB, width, height)
    pixmap.SetTopDown(True)
    for y in range(height):
        row = array[y]
        for x in range(width):
            r, g, b = row[x]
            pixmap.SetPixelColor(x, y, Quantity_Color(float(r), float(g), float(b), Quantity_TOC_RGB))
    _ENVIRONMENT = pixmap
    return pixmap


# --- the CLI ---------------------------------------------------------------------------------------


def _json_arg(text: str | None) -> Any:
    if text is None:
        return None
    text = text.strip()
    if text.startswith(("{", "[")):
        return json.loads(text)
    if text.endswith(".json") and Path(text).is_file():
        return json.loads(Path(text).read_text())
    return text


def main(argv: list[str] | None = None) -> int:
    started = time.perf_counter()
    parser = argparse.ArgumentParser(prog="python -m cadgen.engine.render.occt")
    parser.add_argument("document")
    parser.add_argument("out")
    parser.add_argument("--display")
    parser.add_argument("--camera", default="iso")
    parser.add_argument("--grid", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--pose")
    parser.add_argument("--explode", type=float, default=0.0)
    parser.add_argument("--annotation")
    parser.add_argument("--measurements")
    parser.add_argument("--path-trace", type=int, default=0)
    parser.add_argument("--mesh-cache", help="a folder of the engine's XBM buffers (<key>.xbm); else the daemon's")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    display = _json_arg(args.display)
    display = {"mode": display} if isinstance(display, str) else dict(display or {})
    timings: dict[str, float] = {}
    clock = time.perf_counter()
    from cadgen.engine.document import Loaded

    loaded = Loaded(Path(args.document))
    structure = loaded.structure()
    timings["read_xbf"] = time.perf_counter() - clock
    clock = time.perf_counter()
    if args.mesh_cache:
        from cadgen.engine.render.meshes import load

        buffers = load(Path(args.mesh_cache), [p["key"] for p in structure["prototypes"]])
    else:
        from cadgen.engine.render.meshes import from_daemon

        _structure, buffers, _timings = from_daemon(Path(args.document))
    timings["meshes"] = time.perf_counter() - clock
    scene = Scene(Path(args.document), buffers, size=(args.width, args.height), structure=structure,
                  pose=_json_arg(args.pose))
    timings.update({k: v for k, v in scene.timings.items() if k != "read"})
    if args.explode:
        timings["explode"] = scene.explode(args.explode)
    timings["present"] = scene.show(display, preview=args.preview or bool(args.path_trace))
    camera = display.get("camera") or {}
    projection = camera.get("projection") or ("perspective" if args.preview or args.path_trace else "orthographic")
    camera_arg = _json_arg(args.camera)
    if isinstance(camera_arg, dict) and "camera" in camera_arg and "position" not in camera_arg:
        camera_arg = camera_arg["camera"]  # a prompt's view: its camera
    scene.frame(camera_arg, projection)
    if display.get("grid") or args.grid:
        scene.grid(True)
    if args.annotation:
        scene.annotate(_json_arg(args.annotation))
    if args.measurements:
        scene.measure(_json_arg(args.measurements))
    if args.preview or args.path_trace:
        timings["look"] = scene.preview_look(args.path_trace)
    if args.path_trace:
        timings["frame+encode"] = scene.path_trace(Path(args.out), args.path_trace)
    else:
        timings["frame+encode"] = scene.save(Path(args.out))
    timings["total_in_process"] = time.perf_counter() - started
    if args.json:
        report: dict[str, Any] = {k: round(v, 4) for k, v in timings.items()}
        if scene.fonts:
            report["font"] = ", ".join(sorted(scene.fonts))  # the face the words were set in
        print(json.dumps(report))
    else:
        print(f"wrote {args.out} in {timings['total_in_process']:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
