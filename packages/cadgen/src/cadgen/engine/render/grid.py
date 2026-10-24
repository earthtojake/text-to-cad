"""The CAD Viewer's measuring grid, drawn by OCCT (``occt.py``'s ``Scene.grid``).

The viewer draws the grid as one quad on the plane z = 0 through the world origin, inked by one
fragment shader (core's ``lib/viewer/stageGrid.js``; the snapshot page sizes it from the model at
rest, ``common/renderOptions.js``'s ``addFloor``):

- **Cells** (``paper``): ``framing`` is the model's diameter at rest (the diagonal of its box, each
  side at least 1, the radius at least 1) times the fit's padding, 1.04. The cell is the step of 1,
  2 or 5 x 10^n nearest ``framing / LOOK.grid.cells`` (20) on a log scale; every 5th line (a
  2 x 10^n cell) or 10th is a major.
- **Ink**: one colour (``LOOK.grid.colour``) at 0.45, a minor line at 0.6 of that; a red X axis (the
  line y = 0) and a green Y axis (x = 0) at 0.855, over the major under them.
- **Width**: each line is a box 0.75 (minor), 1.25 (major) or 1.5 (axis) drawing-buffer pixels wide
  filtered by the pixel, a pixel's distance from a line being its distance in the line's coordinate
  over that coordinate's screen derivative (``fwidth``).
- **Fades**: a family of lines fades out as its cells crowd under 8.75 pixels (gone at 3.5), an axis
  as the majors crowd under 8 (gone at 2); the paper dissolves from 1.5 to ``LOOK.grid.extent`` (6)
  framings from the origin, and as the plane turns edge-on to the view (gone at a view direction
  0.01 out of the plane, whole at 0.12): a front view shows none.
- Depth tested against the model, writing no depth, after it; never cut by Clip; none in Preview.
  Three blends it into an 8-bit buffer by the sRGB values themselves.

OCCT's core profile draws lines one pixel wide, so the grid here is geometry: each line a band of
triangles in the plane as wide as the shader's filtered box reaches (its distance in pixels times
``fwidth``, at each sample along the line), its two edges carrying a texture coordinate from one
side of the box to the other. A pixel's samples all read the band's coordinate at the pixel's
centre (multisampling shades a pixel once), which a texture (``profile_texture``) turns into the
shader's ink there: the box's cover at that distance, for the line's kind and fade (the texture's
rows). OCCT blends in linear light (its frame buffer is sRGB); each texel holds the colour and
alpha that, blended over the backdrop in linear light, give what three's blend gives
(``over_backdrop``). Where two lines cross, the bands are blended twice (the shader takes the
stronger): a pixel or so a crossing.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

import numpy as np

from cadgen.engine.render.look import LOOK

# The viewer's numbers: stageGrid.js, autoZoom.js (the fit's padding), renderMeshScene.js (a CAD
# scene's least span and radius).
PADDING = 1.04
MIN_SPAN = 1.0
MIN_RADIUS = 1.0
FADE_START = 1.5
OPACITY = 0.45
AXIS_COLOURS = {"x": "#e5484d", "y": "#2f9e57"}
WIDTH = {"minor": 0.75, "major": 1.25, "axis": 1.5}
STRENGTH = {"minor": 0.6 * OPACITY, "major": OPACITY, "axis": min(1.0, OPACITY * 1.9)}
CROWD = (3.5, 3.5 * 2.5)  # a family of lines: gone with its cells this few pixels apart, whole at this many
AXIS_CROWD = (2.0, 8.0)  # an axis, by the majors' pixels
EDGE_ON = (0.01, 0.12)  # the view direction's share out of the plane: gone, whole
SAMPLES = 97  # along each line, out to the fade's end: an eighth of a framing apart
# The profile texture: a block of rows per kind of line (the Y axis's, then the X axis's, after
# the minors' and majors'), a row per fade level, a column per distance across the line.
KINDS = ("minor", "major", "axis-y", "axis-x")
LEVELS = 33
ACROSS = 64


@dataclass(frozen=True)
class Paper:
    """The grid for a model at rest: its steps and where it fades."""

    cell: float
    major: float
    every: int  # minor cells per major
    framing: float
    fade_start: float
    fade_end: float


def round_step(target: float) -> tuple[float, int]:
    """The step of 1, 2 or 5 x 10^n nearest ``target`` on a log scale, and its leading digit
    (``roundStep(target, true)`` in stageGrid.js: on a tie, the smaller)."""
    exponent = math.floor(math.log10(target))
    best: tuple[float, int] | None = None
    for digit in (1, 2, 5, 10):
        step = digit * 10.0 ** exponent
        if best is None or abs(math.log(step / target)) < abs(math.log(best[0] / target)):
            best = (step, 1 if digit == 10 else digit)
    assert best is not None
    return best


def paper(low: Any, high: Any) -> Paper:
    """The grid of a model whose box at rest is ``low``..``high`` (``buildGridConfig`` at density 1,
    for the radius ``addFloor`` measures)."""
    span = np.maximum(np.asarray(high, float) - np.asarray(low, float), MIN_SPAN)
    radius = max(float(np.linalg.norm(span)) / 2, MIN_RADIUS)
    framing = 2 * radius * PADDING
    cell, digit = round_step(framing / LOOK.grid.cells)
    every = 5 if digit == 2 else 10
    return Paper(cell, cell * every, every, framing, framing * FADE_START, framing * LOOK.grid.extent)


# --- colour ------------------------------------------------------------------------------------


def to_linear(srgb: Any) -> np.ndarray:
    c = np.asarray(srgb, float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(linear: Any) -> np.ndarray:
    c = np.clip(np.asarray(linear, float), 0.0, 1.0)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def hex_colour(value: str) -> np.ndarray:
    value = value.lstrip("#")
    return np.array([int(value[i:i + 2], 16) for i in (0, 2, 4)], float) / 255


def over_backdrop(target: Any, backdrop: Any, alpha: Any) -> tuple[np.ndarray, np.ndarray]:
    """The linear colour and the alpha that, blended over ``backdrop`` (sRGB) in linear light, give
    ``target`` (sRGB, (n, 3)): ``alpha`` (three's) where a colour within 0..1 can, else the least
    alpha that can."""
    goal, under = to_linear(target), to_linear(backdrop)
    with np.errstate(divide="ignore", invalid="ignore"):
        darker = np.where(under > 0, (under - goal) / under, 0.0)
        lighter = np.where(under < 1, (goal - under) / (1 - under), 0.0)
    least = np.where(goal < under, darker, lighter).max(-1)
    blend = np.clip(np.maximum(np.asarray(alpha, float), least), 0.0, 1.0)
    colour = np.clip(under + (goal - under) / np.maximum(blend, 1e-9)[..., None], 0.0, 1.0)
    return colour, blend


def _cover(width: float, distance: np.ndarray) -> np.ndarray:
    """A line's box ``width`` pixels wide, filtered by the pixel, at ``distance`` pixels from it."""
    return np.clip(0.5 * width + 0.5 - np.abs(distance), 0.0, min(width, 1.0))


def _reach(kind: str) -> float:
    """How far from a line its filtered box reaches, in pixels."""
    return 0.5 * WIDTH[kind.partition("-")[0]] + 0.5


def profile(backdrop: str) -> np.ndarray:
    """The texels of ``profile_texture``: (len(KINDS) * LEVELS, ACROSS, 4) of sRGB colour and alpha,
    row ``block * LEVELS + level`` a kind of line at fade ``level / (LEVELS - 1)``, column ``i`` the
    distance ``-reach + 2 * reach * i / (ACROSS - 1)`` across the line."""
    ink, under = hex_colour(LOOK.grid.colour), hex_colour(backdrop)
    fade = np.linspace(0.0, 1.0, LEVELS)[:, None]
    blocks = []
    for kind in KINDS:
        reach = _reach(kind)
        across = np.linspace(-reach, reach, ACROSS)[None, :]
        if kind.startswith("axis"):
            # The shader's mix, in linear light, then encoded: the axis over the major under it.
            axis = STRENGTH["axis"] * fade * _cover(WIDTH["axis"], across)
            grid = STRENGTH["major"] * fade * _cover(WIDTH["major"], across)
            alpha = axis + grid * (1 - axis)
            mixed = (to_linear(hex_colour(AXIS_COLOURS[kind[-1]])) * axis[..., None]
                     + to_linear(ink) * (grid * (1 - axis))[..., None]) / np.maximum(alpha, 1e-9)[..., None]
            shade = to_srgb(mixed)
        else:
            alpha = STRENGTH[kind] * fade * _cover(WIDTH[kind], across)
            shade = np.broadcast_to(ink, alpha.shape + (3,))
        target = under + alpha[..., None] * (shade - under)  # three's blend, of the sRGB values
        colour, blend = over_backdrop(target.reshape(-1, 3), under, alpha.reshape(-1))
        colour, blend = colour.reshape(alpha.shape + (3,)), blend.reshape(alpha.shape)
        # Texels without alpha take the colour of the inked texel nearest them, so filtering
        # between the two fades the alpha and not the colour (row 0 the colour of row 1).
        middle = ACROSS // 2
        for row in range(1, LEVELS):
            inked = np.nonzero(blend[row] > 0)[0]
            if len(inked):
                nearest = inked[np.abs(np.arange(ACROSS)[:, None] - inked[None, :]).argmin(1)]
                colour[row] = colour[row, nearest]
            else:
                colour[row] = colour[row, middle]
        colour[0] = colour[1]
        blocks.append(np.concatenate([to_srgb(colour), blend[..., None]], -1))
    return np.concatenate(blocks)


_TEXTURES: dict[str, Any] = {}


def profile_texture(backdrop: str) -> Any:
    """``profile`` as an OCCT texture: sampled bilinearly, never mipmapped (a band a few pixels
    wide reads the texel at its pixel's distance, as the shader computes it there), its bytes sRGB
    as OCCT reads a colour texture's. Made once a backdrop."""
    found = _TEXTURES.get(backdrop)
    if found is not None:
        return found
    from OCP.Graphic3d import Graphic3d_LevelOfTextureAnisotropy, Graphic3d_Texture2D, Graphic3d_TypeOfTextureFilter
    from OCP.Image import Image_Format, Image_PixMap
    from OCP.Quantity import Quantity_ColorRGBA

    texels = profile(backdrop)
    pixmap = Image_PixMap()
    pixmap.InitZero(Image_Format.Image_Format_RGBA, texels.shape[1], texels.shape[0])
    for y, row in enumerate(texels.tolist()):
        for x, (r, g, b, a) in enumerate(row):
            pixmap.SetPixelColor(x, y, Quantity_ColorRGBA(r, g, b, a), False)
    texture = Graphic3d_Texture2D(pixmap)
    params = texture.GetParams()
    params.SetFilter(Graphic3d_TypeOfTextureFilter.Graphic3d_TOTF_BILINEAR)
    params.SetAnisoFilter(Graphic3d_LevelOfTextureAnisotropy.Graphic3d_LOTA_OFF)
    params.SetRepeat(False)
    params.SetModulate(True)
    texture.SetMipmapsGeneration(False)
    _TEXTURES[backdrop] = texture
    return texture


def _texel_v(block: int, fade: np.ndarray) -> np.ndarray:
    """The texture's v for a kind's block at ``fade`` (0..1): its rows' centres, row 0 at the top."""
    row = block * LEVELS + np.clip(fade, 0.0, 1.0) * (LEVELS - 1)
    return 1 - (row + 0.5) / (len(KINDS) * LEVELS)


# --- the camera ---------------------------------------------------------------------------------


def smoothstep(edge0: float, edge1: float, x: Any) -> np.ndarray:
    t = np.clip((np.asarray(x, float) - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


class Lens:
    """The framed camera (``Scene.frame``'s record) as a map from the plane z = 0 to output pixels
    (x right, y down): where a plane point lands, and the derivative there."""

    def __init__(self, camera: dict[str, Any], width: int, height: int) -> None:
        self.width, self.height = width, height
        self.right, self.up = np.asarray(camera["right"], float), np.asarray(camera["up"], float)
        self.back = np.asarray(camera["direction"], float)  # from the target towards the eye
        self.eye, self.target = np.asarray(camera["eye"], float), np.asarray(camera["target"], float)
        self.perspective = camera["projection"] == "perspective"
        if self.perspective:
            self.focal = (height / 2) / math.tan(math.radians(camera["fov"]) / 2)
        else:
            self.pixel = camera["scale"] / height  # world units a pixel

    def _relative(self, xy: np.ndarray) -> np.ndarray:
        return np.column_stack([xy, np.zeros(len(xy))]) - (self.eye if self.perspective else self.target)

    def depth(self, xy: np.ndarray) -> np.ndarray:
        """How far in front of the eye (perspective; else everywhere 1)."""
        return -(self._relative(xy) @ self.back) if self.perspective else np.ones(len(xy))

    def screen(self, xy: np.ndarray) -> np.ndarray:
        v = self._relative(xy)
        if self.perspective:
            depth = np.maximum(-(v @ self.back), 1e-12)
            return np.column_stack([self.width / 2 + self.focal * (v @ self.right) / depth,
                                    self.height / 2 - self.focal * (v @ self.up) / depth])
        return np.column_stack([self.width / 2 + (v @ self.right) / self.pixel,
                                self.height / 2 - (v @ self.up) / self.pixel])

    def fwidth(self, xy: np.ndarray) -> np.ndarray:
        """``fwidth`` of the plane's x and of its y at each point: |d/dpx| + |d/dpy|, in plane units
        a pixel ((n, 2); infinite where the plane is edge-on)."""
        r, u, b = self.right[:2], self.up[:2], self.back[:2]
        if self.perspective:
            v = self._relative(xy)
            depth = np.maximum(-(v @ self.back), 1e-12)[:, None]
            a, c = (v @ self.right)[:, None], (v @ self.up)[:, None]
            jx = self.focal * (r * depth + a * b) / depth ** 2  # d(pixel x)/d(x, y)
            jy = -self.focal * (u * depth + c * b) / depth ** 2
        else:
            jx = np.broadcast_to(r / self.pixel, (len(xy), 2))
            jy = np.broadcast_to(-u / self.pixel, (len(xy), 2))
        det = jx[:, 0] * jy[:, 1] - jx[:, 1] * jy[:, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            # The inverse's rows: d(x)/d(px, py) and d(y)/d(px, py).
            fx = (np.abs(jy[:, 1]) + np.abs(jx[:, 1])) / np.abs(det)
            fy = (np.abs(jy[:, 0]) + np.abs(jx[:, 0])) / np.abs(det)
        return np.column_stack([np.where(det != 0, fx, np.inf), np.where(det != 0, fy, np.inf)])

    def facing(self, xy: np.ndarray) -> np.ndarray:
        """How far the view direction leaves the plane at each point (|z| of the unit vector to the eye)."""
        if not self.perspective:
            return np.full(len(xy), abs(self.back[2]))
        v = -self._relative(xy)
        return np.abs(v[:, 2]) / np.maximum(np.linalg.norm(v, axis=1), 1e-12)


# --- the lines ----------------------------------------------------------------------------------


@dataclass
class Bands:
    """The grid as triangles: vertices (n, 3), their texture coordinates (n, 2) into
    ``profile_texture``, and triangles (m, 3) of 0-based vertex indices, in drawing order."""

    points: np.ndarray
    texels: np.ndarray
    triangles: np.ndarray


def bands(sheet: Paper, lens: Lens) -> Bands:
    """Every line's visible stretches as bands of triangles in the plane z = 0, for ``lens``."""
    points, texels, triangles = [], [], []
    if lens.perspective or abs(lens.back[2]) > EDGE_ON[0]:  # an orthographic view of the edge: none
        n = int(sheet.fade_end // sheet.cell)
        minors = [k * sheet.cell for k in range(-n, n + 1) if k % sheet.every]
        m = int(sheet.fade_end // sheet.major)
        majors = [k * sheet.major for k in range(-m, m + 1) if k or not LOOK.grid.axes]
        lines = [("minor", [(family, value) for family in (0, 1) for value in minors]),
                 ("major", [(family, value) for family in (0, 1) for value in majors])]
        if LOOK.grid.axes:
            lines += [("axis-y", [(0, 0.0)]), ("axis-x", [(1, 0.0)])]  # the X axis drawn over the Y
        count = 0
        for kind, chosen in lines:
            for vertices, uv, faces in _kind_bands(kind, chosen, sheet, lens):
                points.append(vertices)
                texels.append(uv)
                triangles.append(faces + count)
                count += len(vertices)
    if not points:
        return Bands(np.zeros((0, 3)), np.zeros((0, 2)), np.zeros((0, 3), np.int64))
    return Bands(np.concatenate(points), np.concatenate(texels), np.concatenate(triangles))


def _kind_bands(kind: str, chosen: list[tuple[int, float]], sheet: Paper,
                lens: Lens) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """One kind of line's bands (vertices, texture coordinates, triangles): each a stretch of a
    line that is inked and on screen, two vertices a sample."""
    family = np.array([f for f, _value in chosen])
    value = np.array([v for _family, v in chosen], float)
    reach_out = np.sqrt(np.maximum(sheet.fade_end ** 2 - value ** 2, 0.0))
    t = np.linspace(-1.0, 1.0, SAMPLES)[None, :] * reach_out[:, None]  # along each line
    xy = np.empty(t.shape + (2,))
    xy[..., 0] = np.where(family[:, None] == 0, value[:, None], t)
    xy[..., 1] = np.where(family[:, None] == 0, t, value[:, None])
    flat = xy.reshape(-1, 2)
    # The line's own coordinate's fwidth: x for a line x = value, y for y = value.
    width = lens.fwidth(flat)[np.arange(len(flat)), np.repeat(family, SAMPLES)].reshape(t.shape)
    reached = 1 - smoothstep(sheet.fade_start, sheet.fade_end, np.linalg.norm(xy, axis=-1))
    seen = smoothstep(*EDGE_ON, lens.facing(flat).reshape(t.shape))
    base = kind.partition("-")[0]
    with np.errstate(divide="ignore", invalid="ignore"):
        keep = (smoothstep(*AXIS_CROWD, sheet.major / width) if base == "axis"
                else smoothstep(*CROWD, (sheet.cell if base == "minor" else sheet.major) / width))
    fade = np.nan_to_num(keep * reached * seen)
    # Where each line is drawn: in front of the eye, inked, on screen.
    usable = (lens.depth(flat).reshape(t.shape) > 0) & np.isfinite(width)
    screen = lens.screen(flat).reshape(t.shape + (2,))
    low, high = np.minimum(screen[:, :-1], screen[:, 1:]), np.maximum(screen[:, :-1], screen[:, 1:])
    margin = 4.0
    off = (high[..., 0] < -margin) | (low[..., 0] > lens.width + margin) | (high[..., 1] < -margin) | \
        (low[..., 1] > lens.height + margin)
    inked = fade > 1e-4
    drawn = (inked[:, :-1] | inked[:, 1:]) & ~off & usable[:, :-1] & usable[:, 1:]
    reach = _reach(kind)
    u = np.array([0.5, ACROSS - 0.5]) / ACROSS  # the first and last columns' centres: -reach, +reach
    block = KINDS.index(kind)
    found = []
    for line in np.nonzero(drawn.any(1))[0]:
        steps = np.diff(np.concatenate([[0], drawn[line].astype(np.int8), [0]]))
        for first, last in zip(np.nonzero(steps == 1)[0], np.nonzero(steps == -1)[0]):
            samples = _needed(np.arange(first, last + 1), fade[line], width[line])
            vertices = np.zeros((len(samples), 2, 3))
            vertices[..., :2] = xy[line, samples][:, None, :]
            vertices[..., family[line]] += np.array([-reach, reach])[None, :] * width[line, samples][:, None]
            uv = np.empty((len(samples), 2, 2))
            uv[..., 0] = u[None, :]
            uv[..., 1] = _texel_v(block, fade[line, samples])[:, None]
            found.append((vertices.reshape(-1, 3), uv.reshape(-1, 2), _band_triangles(len(samples))))
    return found


def _needed(samples: np.ndarray, *series: np.ndarray) -> np.ndarray:
    """The samples a stretch needs: its ends, and every sample where a series is not the straight
    line through its neighbours (an orthographic view's lines are straight but for their fades)."""
    if len(samples) <= 2:
        return samples
    values = np.stack([s[samples] for s in series], -1)
    scale = np.maximum(np.abs(values).max(0), 1e-12)
    bent = (np.abs(values[:-2] - 2 * values[1:-1] + values[2:]) / scale > 1e-7).any(-1)
    return samples[np.concatenate([[True], bent, [True]])]


def _band_triangles(rows: int) -> np.ndarray:
    """Two triangles for each step along a band of two vertices a row."""
    if rows < 2:
        return np.zeros((0, 3), np.int64)
    a = np.arange(rows - 1) * 2
    return np.concatenate([np.stack([a, a + 1, a + 3], 1), np.stack([a, a + 3, a + 2], 1)])


# --- in OCCT -------------------------------------------------------------------------------------


def unclipped() -> Any:
    """A plane list for a presentation that no clip plane of the view cuts."""
    from OCP.Graphic3d import Graphic3d_SequenceOfHClipPlane

    planes = Graphic3d_SequenceOfHClipPlane()
    planes.SetOverrideGlobal(True)
    return planes


def _present(scene: Any, found: Bands) -> Any:
    from OCP.Aspect import Aspect_InteriorStyle, Aspect_PolygonOffsetMode
    from OCP.Graphic3d import (Graphic3d_AlphaMode, Graphic3d_ArrayFlags_VertexTexel, Graphic3d_ArrayOfTriangles,
                               Graphic3d_AspectFillArea3d, Graphic3d_Group, Graphic3d_Structure,
                               Graphic3d_TypeOfBackfacingModel, Graphic3d_TypeOfShadingModel)
    from OCP.Quantity import Quantity_Color, Quantity_ColorRGBA, Quantity_TOC_RGB

    array = Graphic3d_ArrayOfTriangles(len(found.points), 3 * len(found.triangles), Graphic3d_ArrayFlags_VertexTexel)
    add = array.AddVertex
    for (x, y, z), (u, v) in zip(found.points.tolist(), found.texels.tolist()):
        add(x, y, z, u, v)
    edges = array.AddTriangleEdges
    for a, b, c in (found.triangles + 1).tolist():
        edges(a, b, c)
    aspect = Graphic3d_AspectFillArea3d()
    aspect.SetInteriorStyle(Aspect_InteriorStyle.Aspect_IS_SOLID)
    aspect.SetShadingModel(Graphic3d_TypeOfShadingModel.Graphic3d_TypeOfShadingModel_Unlit)
    aspect.SetInteriorColor(Quantity_ColorRGBA(Quantity_Color(1, 1, 1, Quantity_TOC_RGB), 1.0))
    aspect.SetAlphaMode(Graphic3d_AlphaMode.Graphic3d_AlphaMode_Blend, 0.5)
    aspect.SetFaceCulling(Graphic3d_TypeOfBackfacingModel.Graphic3d_TypeOfBackfacingModel_DoubleSided)
    # As the viewer's: a model face on the plane wins over it, the faces stepping back as far.
    aspect.SetPolygonOffsets(Aspect_PolygonOffsetMode.Aspect_POM_Fill, 1.0, 1.0)
    aspect.SetTextureMap(profile_texture(LOOK.backdrop))
    aspect.SetTextureMapOn(True)
    structure = Graphic3d_Structure(scene.canvas.viewer.StructureManager())
    group = structure.NewGroup()
    group.SetGroupPrimitivesAspect(aspect)
    Graphic3d_Group.AddPrimitiveArray(group, array)
    structure.SetClipPlanes(unclipped())
    structure.Display()
    return structure


def show(scene: Any, on: bool = True) -> float:
    """The grid for the camera ``scene`` has framed (call it after ``frame``), or none; the seconds
    it took. Preview draws none, as the viewer's."""
    clock = time.perf_counter()
    held = getattr(scene, "grid_structure", None)
    if held is not None:
        held.Erase()
        held.Remove()
        scene.grid_structure = None
    if not on or scene.preview:
        return time.perf_counter() - clock
    if getattr(scene, "camera", None) is None:
        raise RuntimeError("the grid is drawn for a framed camera: frame the scene first")
    low, high = scene.rest_bounds()
    found = bands(paper(low, high), Lens(scene.camera, scene.canvas.width, scene.canvas.height))
    if len(found.triangles):
        scene.grid_structure = _present(scene, found)
    return time.perf_counter() - clock
