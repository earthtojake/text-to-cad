"""A DXF drawn by OCCT as the viewer's DXF pane draws it (``@text-to-cad/core`` ``lib/drawing2d``):
the whole drawing from above, fitted to the picture with the pane's margin, or the window a plan
view names (a Quick Edit view's camera: ``plan_view``), its lines one pixel wide in their pens, its
fills flat in theirs, its words in their pens, set in the platform's UI face at their cap height and
painted over the frame (sRGB over, as a canvas paints), the default pen in the look's ink, on the
look's paper (``look.DRAWING``: the light or the dark pair, ``display.appearance``); an
annotation's ink over it, on the sheet, as the pane paints it (``paint_ink``), and Measure's
dimensions over that (``overlay.paint_measurements``, through the view). A drawing has no
scene: no lights, no modes, no camera to turn, no grid, clip, Explode or Preview, and those are
refused by name before anything is drawn.

A drawing is held as a document is (``service.Held``): ``open`` reads it (``formats/dxf.py``) and
makes its shapes -- one compound of polygon edges per pen, one triangulation per fill pen, crafted
as a part's are (``shapes.py``) -- and ``draw`` frames and draws it, warm on its canvas.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Any

import numpy as np

__all__ = ["Held", "paint_ink", "plan_view", "refusals"]

REFUSED = {"mode": "display.mode", "grid": "the grid", "clip": "Clip", "exploded": "Explode",
           "camera": "display.camera (a lens)", "hidden": "display.hidden", "isolated": "display.isolated"}
PLAN_KEYS = frozenset({"position", "target", "up", "orthographicHalfHeight"})
PLAN_TOLERANCE = 1e-6  # how far off straight down, or off +Y up, a plan view may be: rounding, never a tilt
TEXT_LINE_HEIGHT = 1.25  # a text mark's line pitch, of its words' size (``marks.js``)


def plan_view(camera: Any, name: str) -> tuple[float, float, float]:
    """A drawing's camera, checked: its plan view, the window the viewer's drawing pane shows in the
    camera shape every view speaks (``lib/drawing2d/planView.js``'s ``planCamera``) -- looking
    straight down at the sheet, +Y up, centred on ``target``, ``orthographicHalfHeight`` drawing
    units above and below. Its centre and half height; any other camera is refused by name."""
    from cadgen.engine.snapshot import SnapshotRefused, _numbers

    refused = SnapshotRefused(
        f"{name} is a drawing, seen from above: its camera is a plan view, {{\"position\": [x, y, d], \"target\": "
        "[x, y, 0], \"up\": [0, 1, 0], \"orthographicHalfHeight\": h}, looking straight down at the sheet with +Y up "
        "(the window a Quick Edit view of it names)")
    if not isinstance(camera, dict) or set(camera) - PLAN_KEYS or not _numbers(camera.get("position"), 3) \
            or not _numbers(camera.get("target"), 3) or not _numbers(camera.get("up", [0, 1, 0]), 3):
        raise refused
    look = np.subtract(camera["position"], camera["target"], dtype=float)
    up = np.asarray(camera.get("up", [0, 1, 0]), float)
    half = camera.get("orthographicHalfHeight")
    reach, rise = float(np.linalg.norm(look)), float(np.linalg.norm(up))
    if not (reach > 0 and rise > 0 and abs(look[0]) <= PLAN_TOLERANCE * reach and abs(look[1]) <= PLAN_TOLERANCE * reach
            and look[2] > 0 and abs(up[0]) <= PLAN_TOLERANCE * rise and abs(up[2]) <= PLAN_TOLERANCE * rise and up[1] > 0
            and isinstance(half, (int, float)) and not isinstance(half, bool) and math.isfinite(half) and half > 0):
        raise refused
    return float(camera["target"][0]), float(camera["target"][1]), float(half)


def refusals(still: Any, name: str) -> None:
    """What a drawing does not offer, refused by name before anything renders: its camera, given,
    is a plan view (``plan_view``)."""
    from cadgen.engine.snapshot import SnapshotRefused

    if still.camera is not None:
        plan_view(still.camera, name)
    asked = [key for key in REFUSED if still.display.get(key) not in (None, False)]
    for flag, given in (("--preview", still.preview), ("--pose", still.pose is not None)):
        if given:
            asked.append(flag)
    if asked:
        named = ", ".join(REFUSED.get(key, key) for key in asked)
        raise SnapshotRefused(f"{name} is a drawing, drawn from above in its pens: {named} "
                              f"{'do' if len(asked) > 1 else 'does'} not apply to it. Its display takes appearance "
                              "(light or dark), its camera a plan view, and ink and dimensions lie on its sheet")
    appearance = still.display.get("appearance", "light")
    if appearance not in ("light", "dark"):
        raise SnapshotRefused(f"display.appearance is light or dark, not {appearance!r}")


class Held:
    """One DXF as a renderer holds it: the drawing read, its shapes, a canvas made on first use."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.kind = "dxf"
        self.drawing: Any = None
        self.canvas: Any = None
        self.shown: list[tuple[Any, str | None]] = []  # each presentation and its pen (None: the look's ink)
        self.files: dict[str, Any] = {}
        self.warnings: list[str] = []

    def open(self) -> dict[str, Any]:
        from cadgen.engine.formats.dxf import read_dxf

        started = time.perf_counter()
        self.close()
        self.drawing = read_dxf(self.path)
        self.files, self.warnings = self.drawing.files, self.drawing.warnings
        return {"readMs": round((time.perf_counter() - started) * 1000), "kind": "dxf", "files": self.files,
                "warnings": self.warnings, "entities": self.drawing.entities}

    def close(self) -> None:
        if self.canvas is not None:
            self.canvas.close()
        self.canvas, self.shown = None, []

    def _show(self) -> None:
        """Each pen's lines and fills as one presentation: fills under the lines, every one unlit."""
        from OCP.AIS import AIS_Shape
        from OCP.Graphic3d import Graphic3d_TypeOfShadingModel

        from cadgen.engine.render.shapes import craft, read

        bounds = self.drawing.bounds
        depth = max(bounds[2] - bounds[0], bounds[3] - bounds[1], 1e-9) * 1e-4 if bounds else 1.0
        pens: dict[str | None, list[np.ndarray]] = {}
        for points, pen in self.drawing.lines:
            pens.setdefault(pen, []).append(points)
        fills: dict[str | None, list[np.ndarray]] = {}
        for triangles, pen in self.drawing.fills:
            fills.setdefault(pen, []).append(triangles)
        context = self.canvas.context
        for pen, chunks in fills.items():
            triangles = np.concatenate(chunks).reshape(-1, 2)
            nodes = np.column_stack([triangles, np.full(len(triangles), -depth)])
            shown = AIS_Shape(read(craft([(nodes, np.arange(len(nodes)).reshape(-1, 3), None)], {})))
            shown.Attributes().SetupOwnShadingAspect()
            shown.Attributes().ShadingAspect().Aspect().SetShadingModel(
                Graphic3d_TypeOfShadingModel.Graphic3d_TypeOfShadingModel_Unlit)
            context.Display(shown, 1, -1, False)
            self.shown.append((shown, pen))
        for pen, chunks in pens.items():
            counts = np.array([len(chunk) for chunk in chunks])
            points = np.column_stack([np.concatenate(chunks), np.zeros(int(counts.sum()))])
            shown = AIS_Shape(read(craft([], {"feature": (points, counts)})))
            context.Display(shown, 0, -1, False)
            self.shown.append((shown, pen))

    def draw(self, still: Any) -> tuple[bytes, dict[str, Any]]:
        """``still`` (a ``snapshot.Still``) drawn: the PNG's bytes and what was drawn."""
        from OCP.Graphic3d import Graphic3d_Camera
        from OCP.gp import gp_Dir, gp_Pnt

        from cadgen.engine.render.context import Canvas
        from cadgen.engine.render.look import DRAWING
        from cadgen.engine.render.occt import _color, occt_scale
        from cadgen.engine.render.overlay import REFERENCE_HEIGHT, paint_measurements
        from cadgen.engine.render.service import finished, picture

        if self.drawing is None:
            raise RuntimeError("the renderer holds no drawing")
        refusals(still, self.path.name)
        started = time.perf_counter()
        timings: dict[str, int] = {}
        width, height = still.drawn  # supersampled (a job's renderScale), brought down after (``picture``)
        appearance = still.display.get("appearance", "light")
        paper, ink = DRAWING.paper(appearance)
        if self.canvas is None:
            clock = time.perf_counter()
            self.canvas = Canvas(width, height)
            params = self.canvas.view.ChangeRenderingParams()
            # Hairlines aliased, a pixel wide, as a 2D CAD viewer draws them: multisampled 1-pixel
            # lines broke into dots on Mesa's llvmpipe, and drawn larger and brought down
            # (RenderResolutionScale) they come out a quarter as dark, since a core-profile context
            # draws no line wider than a pixel.
            params.NbMsaaSamples = 0
            self._show()
            timings["sceneMs"] = round((time.perf_counter() - clock) * 1000)
        self.canvas.width, self.canvas.height = width, height
        for shown, pen in self.shown:
            shown.SetColor(_color(pen or ink))
            shown.SetWidth(DRAWING.line_width)
        self.canvas.view.SetBackgroundColor(_color(paper))
        bounds = self.drawing.bounds or (0.0, 0.0, 1.0, 1.0)
        span_x, span_y = abs(bounds[2] - bounds[0]), abs(bounds[3] - bounds[1])
        if still.camera is not None:  # a plan view: the window it names, its half height half the picture's
            centre_x, centre_y, half = plan_view(still.camera, self.path.name)
            centre, scale = (centre_x, centre_y), height / (2 * half)
        else:  # the whole drawing, fitted with the pane's margin
            margin = DRAWING.margin * still.scale
            usable_x = max(width - 2 * margin, width * 0.5)
            usable_y = max(height - 2 * margin, height * 0.5)
            scale = min(usable_x / span_x if span_x > 0 else np.inf, usable_y / span_y if span_y > 0 else np.inf)
            scale = scale if np.isfinite(scale) and scale > 0 else 1.0  # pixels a unit, the pane's fit
            centre = ((bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2)
        camera = self.canvas.view.Camera()
        camera.SetProjectionType(Graphic3d_Camera.Projection_e.Projection_Orthographic)
        camera.SetAspect(width / height)
        reach = max(span_x, span_y, 1.0)
        camera.SetEyeAndCenter(gp_Pnt(centre[0], centre[1], reach), gp_Pnt(centre[0], centre[1], 0.0))
        camera.SetUp(gp_Dir(0, 1, 0))
        camera.SetScale(occt_scale(height / scale, width / height))
        self.canvas.view.ZFitAll(1.0)
        clock = time.perf_counter()
        texts = self.drawing.texts

        def place(point: Any) -> tuple[float, float]:
            return ((point[0] - centre[0]) * scale + width / 2, height / 2 - (point[1] - centre[1]) * scale)

        view = self.canvas.view
        marks = (still.annotation or {}).get("marks") or []
        dimensions = still.measurements or []

        def paint(frame: np.ndarray) -> None:  # the words, the ink over them, Measure's dimensions over all
            if texts:
                paint_words(frame, texts, place, scale, ink)
            if marks:
                paint_ink(frame, marks, place, height / REFERENCE_HEIGHT)
            if dimensions:
                paint_measurements(frame, dimensions, lambda points: np.array([place(point) for point in points]))

        def backdrop(colour: Any) -> None:  # the paper, or (a transparent picture's matte) black and white
            view.SetBackgroundColor(_color(paper if colour is None else tuple(colour)))

        data = picture(self.canvas, paint if texts or marks or dimensions else None, still, backdrop)
        timings["drawMs"] = round((time.perf_counter() - clock) * 1000)
        timings["renderMs"] = round((time.perf_counter() - started) * 1000)
        return data, {"width": still.size[0], "height": still.size[1], **finished(still),
                      "camera": "plan" if still.camera is not None else "top", "projection": "orthographic",
                      "displayMode": "drawing", "appearance": appearance, "preview": False,
                      "entities": self.drawing.entities, "layers": self.drawing.layers,
                      "lines": len(self.drawing.lines), "fills": len(self.drawing.fills),
                      "texts": len(self.drawing.texts), "pose": None,
                      "exploded": None, "unmeshed": {}, "renderer": "occt", "kind": "dxf",
                      "warnings": self.warnings, "timings": timings}


def paint_words(frame: np.ndarray, texts: list[Any], place: Any, scale: float, ink: str) -> None:
    """Each text's lines over ``frame`` (sRGB bytes, rows top first, in place): set in the face at
    their cap height in pixels, stretched by their width factor, turned to their direction about
    each line's baseline start (``place``: drawing to pixels), laid over in their pen's colour."""
    import math

    from PIL import Image, ImageDraw

    from cadgen.engine.formats.dxf import cap_per_em, font

    height, width = frame.shape[:2]
    for text in texts:
        size = text.height / cap_per_em() * scale
        if size < 1:
            continue
        face = font(size)
        ascent, descent = face.getmetrics()
        rgb = np.array([int((text.pen or ink)[at:at + 2], 16) for at in (1, 3, 5)], float)
        angle = math.degrees(math.atan2(text.direction[1], text.direction[0]))
        for line, start in zip(text.lines, text.starts):
            if not line.strip():
                continue
            pad = 2
            mask = Image.new("L", (int(math.ceil(face.getlength(line))) + 2 * pad, ascent + descent + 2 * pad), 0)
            ImageDraw.Draw(mask).text((pad, pad + ascent), line, fill=255, font=face, anchor="ls")
            anchor = np.array([pad, pad + ascent], float)
            if abs(text.width - 1) > 1e-6:
                mask = mask.resize((max(1, round(mask.width * text.width)), mask.height), Image.BICUBIC)
                anchor[0] *= text.width
            centre = np.array([mask.width / 2, mask.height / 2])
            turned = mask.rotate(angle, resample=Image.BICUBIC, expand=True)
            theta = math.radians(angle)
            offset = anchor - centre
            moved = np.array([offset[0] * math.cos(theta) + offset[1] * math.sin(theta),
                              -offset[0] * math.sin(theta) + offset[1] * math.cos(theta)])
            at = np.array(place(start)) - (np.array([turned.width / 2, turned.height / 2]) + moved)
            left, top = int(round(at[0])), int(round(at[1]))
            cover = np.asarray(turned, float) / 255.0
            x0, y0 = max(left, 0), max(top, 0)
            x1, y1 = min(left + turned.width, width), min(top + turned.height, height)
            if x1 <= x0 or y1 <= y0:
                continue
            alpha = cover[y0 - top:y1 - top, x0 - left:x1 - left, None]
            region = frame[y0:y1, x0:x1].astype(float)
            frame[y0:y1, x0:x1] = np.rint(region * (1 - alpha) + rgb * alpha).astype(np.uint8)


INK_SUPERSAMPLE = 4  # a mark's coverage is taken on this many samples a pixel, each way


def _laid(frame: np.ndarray, left: int, top: int, cover: np.ndarray, rgb: np.ndarray, opacity: float) -> None:
    """``cover`` (0 to 1, rows top first) laid over ``frame`` at ``(left, top)`` in ``rgb``, at
    ``opacity``, sRGB over, as a canvas composites; what falls outside the frame is dropped."""
    height, width = frame.shape[:2]
    x0, y0 = max(left, 0), max(top, 0)
    x1, y1 = min(left + cover.shape[1], width), min(top + cover.shape[0], height)
    if x1 <= x0 or y1 <= y0:
        return
    alpha = cover[y0 - top:y1 - top, x0 - left:x1 - left, None] * opacity
    region = frame[y0:y1, x0:x1].astype(float)
    frame[y0:y1, x0:x1] = np.rint(region * (1 - alpha) + rgb * alpha).astype(np.uint8)


def paint_ink(frame: np.ndarray, marks: list[dict[str, Any]], place: Any, line_scale: float) -> None:
    """An annotation's ink over a drawing (sRGB bytes, rows top first, in place), as the viewer's
    drawing pane paints it (``@text-to-cad/core`` ``lib/drawing2d/marks.js``): each mark on the sheet,
    its points in drawing coordinates placed through the view (``place``: drawing to pixels), in its
    colour at its opacity. A stroke is round-capped and -joined, ``width`` pixels times ``line_scale``
    wide (the picture as heavy as the viewer was against its height; a segment of a stroke with
    ``widths`` the mean of its two ends'); an area is its outline filled; a text mark's words fill the
    box of its four corners, set in the face the pane sets them in, line after line."""
    from PIL import Image, ImageDraw

    from cadgen.engine.render.text import coverage, face

    ss = INK_SUPERSAMPLE
    for mark in marks:
        screen = np.array([place(point) for point in np.asarray(mark["points"], float).reshape(-1, 3)], float)
        rgb = np.array([int(mark["color"][at:at + 2], 16) for at in (1, 3, 5)], float)
        opacity = float(mark.get("opacity", 1.0))
        if mark["kind"] == "text":
            _paint_text(frame, mark, screen, rgb, opacity, coverage, face)
            continue
        if mark["kind"] == "area":
            screen, reach = screen[:int(mark.get("outline") or len(screen))], 1.0
        else:
            widths = mark.get("widths")
            shares = (np.asarray(widths, float) if widths and len(widths) == len(screen)
                      else np.ones(len(screen)))
            if mark.get("closed"):
                screen, shares = np.vstack([screen, screen[:1]]), np.append(shares, shares[:1])
            ends = float(mark.get("width") or 0) * line_scale * shares
            reach = float(ends.max(initial=0.0)) / 2 + 1.0
        if not len(screen):
            continue
        left, top = (int(math.floor(value - reach)) for value in screen.min(0))
        right, bottom = (int(math.ceil(value + reach)) for value in screen.max(0))
        height, width = frame.shape[:2]  # ink beyond the frame is never seen; clip before allocating
        margin = int(math.ceil(reach)) + 1
        left, top = max(left, -margin), max(top, -margin)
        right, bottom = min(right, width + margin), min(bottom, height + margin)
        if right <= left or bottom <= top:
            continue
        mask = Image.new("L", ((right - left) * ss, (bottom - top) * ss), 0)
        draw = ImageDraw.Draw(mask)
        local = [((x - left) * ss, (y - top) * ss) for x, y in screen]
        if mark["kind"] == "area":
            if len(local) >= 3:
                draw.polygon(local, fill=255)
        else:
            for at, (start, end) in enumerate(zip(local, local[1:] or local)):
                wide = (ends[at] + ends[min(at + 1, len(ends) - 1)]) / 2 * ss
                if wide <= 0:
                    continue
                draw.line([start, end], fill=255, width=max(1, round(wide)))
                for x, y in (start, end):  # round caps and joins
                    draw.ellipse([x - wide / 2, y - wide / 2, x + wide / 2, y + wide / 2], fill=255)
        cover = np.asarray(mask.reduce(ss), float) / 255.0
        _laid(frame, left, top, cover, rgb, opacity)


def _paint_text(frame: np.ndarray, mark: dict[str, Any], corners: np.ndarray, rgb: np.ndarray, opacity: float,
                coverage: Any, face: Any) -> None:
    """A text mark's words filling the box of its corners (0 its top-left, 1 its top-right, 3 its
    bottom-left), as the pane fills it: a line's em box its height over the line pitch, the face's
    weight 500, the lines from the box's top, the box turned and stretched as its corners lie."""
    from PIL import Image

    if len(corners) != 4:
        return
    a, b, d = corners[0], corners[1], corners[3]
    across, down = float(np.linalg.norm(b - a)), float(np.linalg.norm(d - a))
    lines = str(mark.get("text", "")).split("\n")
    if not (across > 0 and down > 0) or not any(line.strip() for line in lines):
        return
    size = down / (len(lines) * TEXT_LINE_HEIGHT)
    if size < 1:
        return
    local = coverage(lines, face(500, size), (int(math.ceil(across)) + 2, int(math.ceil(down)) + 2), (0.0, 0.0),
                     size * TEXT_LINE_HEIGHT)
    # The box's own frame (u along its top, v down its side) laid on the picture through its corners.
    basis = np.column_stack([(b - a) / across, (d - a) / down])
    inverse = np.linalg.inv(basis)
    left, top = (int(math.floor(value)) - 1 for value in corners.min(0))
    right, bottom = (int(math.ceil(value)) + 1 for value in corners.max(0))
    # Each pixel of the box's region read from the box's frame: (u, v) = inverse . (pixel - a).
    shift = inverse @ (np.array([left, top], float) - a)
    coefficients = (inverse[0, 0], inverse[0, 1], shift[0], inverse[1, 0], inverse[1, 1], shift[1])
    picture = Image.fromarray(np.rint(local * 255).astype(np.uint8), "L")
    laid = picture.transform((right - left, bottom - top), Image.Transform.AFFINE, coefficients,
                             resample=Image.Resampling.BILINEAR)
    _laid(frame, left, top, np.asarray(laid, float) / 255.0, rgb, opacity)
