"""A DXF read with the standard library, as the stills draw it: a top view of what its modelspace
draws -- lines, arcs, circles, polylines (with bulges), ellipses, splines, solids and solid
hatches, and the blocks inserts and dimensions place -- each in its pen: its true colour, its
ACI colour (ezdxf's palette, which the viewer's payload resolves it by), its block's or its
layer's; ACI 7, the pen that contrasts with the paper, is the default pen (``None``), drawn in
the look's ink. A layer that is off or frozen draws nothing, as the viewer has it.

A curve is drawn as a polyline fine enough to look round (``SEGMENTS`` to a turn, at least
``MINIMUM`` to a curve); a spline is the kernel's B-spline (``Geom_BSplineCurve``) of its control
points, knots and weights, or the cubic CAD programs make through its fit points; a solid hatch is its boundary
loops filled even-odd (the kernel's face of its outer loop and holes, meshed). Text (TEXT, MTEXT
and an insert's ATTRIB) is laid out in the plane as the viewer's pane sets it: in the platform's UI
face (``render/text.py``), its cap height the entity's height, its width factor, rotation and
alignment (MTEXT: its attachment, its paragraphs, its formatting codes dropped), and painted over
the picture (``render/drawing.py``). Points, hatch patterns, images and 3D entities are not drawn,
and are counted (``Drawing.skipped``) for the snapshot to say so.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from cadgen.engine.formats import FormatError, files_of

__all__ = ["Drawing", "DxfError", "read_dxf"]

SEGMENTS = 256  # a full turn's segments
MINIMUM = 8  # a curve's fewest
DEFAULT_PEN = 7
# ezdxf's ACI palette (``ezdxf.colors.DXF_DEFAULT_COLORS``), index 0 to 255, three bytes each.
ACI = bytes.fromhex(
    "000000ff0000ffff0000ff0000ffff0000ffff00ffffffff808080c0c0c0ff0000ff7f7fa50000a552527f00007f3f3f4c00004c"
    "2626260000261313ff3f00ff9f7fa52900a567527f1f007f4f3f4c13004c2f26260900261713ff7f00ffbf7fa55200a57c527f3f"
    "007f5f3f4c26004c3926261300261c13ffbf00ffdf7fa57c00a591527f5f007f6f3f4c39004c4226261c00262113ffff00ffff7f"
    "a5a500a5a5527f7f007f7f3f4c4c004c4c26262600262613bfff00dfff7f7ca50091a5525f7f006f7f3f394c00424c261c260021"
    "26137fff00bfff7f52a5007ca5523f7f005f7f3f264c00394c261326001c26133fff009fff7f29a50067a5521f7f004f7f3f134c"
    "002f4c2609260017261300ff007fff7f00a50052a552007f003f7f3f004c00264c2600260013261300ff3f7fff9f00a52952a567"
    "007f1f3f7f4f004c13264c2f00260913581700ff7f7fffbf00a55252a57c007f3f3f7f5f004c26264c3900261313581c00ffbf7f"
    "ffdf00a57c52a591007f5f3f7f6f004c39264c4200261c13585800ffff7fffff00a5a552a5a5007f7f3f7f7f004c4c264c4c0026"
    "2613585800bfff7fdfff007ca55291a5005f7f3f6f7f00394c26427e001c26135858007fff7fbfff0052a5527ca5003f7f3f5f7f"
    "00264c26397e001326131c58003fff7f9fff0029a55267a5001f7f3f4f7f00134c262f7e0009261317580000ff7f7fff0000a552"
    "52a500007f3f3f7f00004c26267e0000261313583f00ff9f7fff2900a56752a51f007f4f3f7f13004c2f267e0900261713587f00"
    "ffbf7fff5200a57c52a53f007f5f3f7f26004c39267e1300261c1358bf00ffdf7fff7c00a59152a55f007f6f3f7f39004c42264c"
    "1c0026581358ff00ffff7fffa500a5a552a57f007f7f3f7f4c004c4c264c260026581358ff00bfff7fdfa5007ca552917f005f7f"
    "3f6f4c00394c264226001c581358ff007fff7fbfa50052a5527c7f003f7f3f5f4c00264c263926001358131cff003fff7f9fa500"
    "29a552677f001f7f3f4f4c00134c262f260009581317000000656565666666999999ccccccffffff"
)
DRAWN = {"LINE", "CIRCLE", "ARC", "LWPOLYLINE", "POLYLINE", "ELLIPSE", "SPLINE", "SOLID", "TRACE", "HATCH", "INSERT",
         "DIMENSION", "LEADER", "RAY", "XLINE", "TEXT", "MTEXT", "ATTRIB"}
CAP_PER_EM = 0.7  # a face's cap height in ems, where the face does not say (the pane's fallback)
LINE_SPACING = 5 / 3  # MTEXT's line pitch in cap heights, at its spacing factor 1
SPECIALS = {"%%d": "\u00b0", "%%p": "\u00b1", "%%c": "\u00d8", "%%%": "%", "%%u": "", "%%o": "", "%%k": ""}
# A block is drawn once for every insert of it (and every cell of a MINSERT's grid), and its own
# inserts again inside it, so a few kilobytes can name an exponential drawing. A read draws at
# most this many entities, its blocks' members counted once for each place they are drawn, and
# nests blocks at most this deep.
MAX_EXPANDED = 1_000_000
MAX_BLOCK_DEPTH = 16


class DxfError(FormatError):
    """A file that does not read as a DXF, said by name."""


@dataclass
class Text:
    """Words in the plane: their lines, each line's baseline start (drawing units), the direction
    the lines run (a unit vector), the cap height and the width factor, and the pen."""

    lines: list[str]
    starts: list[tuple[float, float]]
    direction: tuple[float, float]
    height: float
    width: float
    pen: str | None

    def corners(self) -> np.ndarray:
        """The box of every line (baseline to cap height, start to its measured end), its corners."""
        direction = np.asarray(self.direction, float)
        up = np.array([-direction[1], direction[0]])
        found = []
        for line, start in zip(self.lines, self.starts):
            length = measure(line, self.height) * self.width
            for along, rise in ((0, -0.25), (length, -0.25), (length, 1.0), (0, 1.0)):
                found.append(np.asarray(start) + direction * along + up * rise * self.height)
        return np.array(found)


def font(size: float) -> Any:
    """The platform's UI face (``render/text.py``'s) at ``size`` pixels to the em, regular."""
    from cadgen.engine.render.text import _pillow_font, face

    found = face(400, 100.0)
    return _pillow_font(found.path, float(size), found.values)


def measure(line: str, height: float) -> float:
    """A line's length in drawing units at cap height ``height``, in the platform's UI face."""
    return float(font(100.0).getlength(line)) / 100.0 * height / cap_per_em()


@lru_cache(maxsize=1)
def cap_per_em() -> float:
    """The face's cap height in ems: its H's top above the baseline, measured; else ``CAP_PER_EM``."""
    try:
        top = -font(100.0).getbbox("H", anchor="ls")[1] / 100.0
    except Exception:  # noqa: BLE001 - a face without the glyph: the pane's own fallback
        return CAP_PER_EM
    return top if 0.3 < top < 1.0 else CAP_PER_EM


def _words(text: str) -> str:
    for code, char in SPECIALS.items():
        text = text.replace(code, char).replace(code.upper(), char)
    return text


def _paragraphs(text: str) -> list[str]:
    """MTEXT's words as lines: its paragraphs (``\\P``), its formatting codes and braces dropped,
    a stacked fraction (``\\Sa^b;``) as ``a/b``."""
    import re

    text = text.replace("\\\\", "\x00").replace("\\{", "\x01").replace("\\}", "\x02")
    text = re.sub(r"\\S([^;^#/]*)[\^#/]([^;]*);", r"\1/\2", text)
    text = re.sub(r"\\[fFHWQTACcpa][^;]*;", "", text)
    text = re.sub(r"\\[LlOoKkNX]", "", text)
    text = text.replace("\\P", "\n").replace("\\~", " ").replace("{", "").replace("}", "")
    text = text.replace("\x00", "\\").replace("\x01", "{").replace("\x02", "}")
    return _words(text).split("\n")


@dataclass
class Drawing:
    """What the file's modelspace draws, flattened: polylines (``lines``: (N, 2) points and a
    pen) and filled triangles (``fills``: (M, 3, 2) and a pen), a pen ``#rrggbb`` or None for the
    default; their bounds; and what it holds that is not drawn, by entity type."""

    path: Path
    lines: list[tuple[np.ndarray, str | None]] = field(default_factory=list)
    fills: list[tuple[np.ndarray, str | None]] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)
    entities: int = 0
    layers: int = 0
    skipped: Counter = field(default_factory=Counter)
    files: dict[str, tuple[int, int]] = field(default_factory=dict)
    kind: str = "dxf"

    @property
    def bounds(self) -> tuple[float, float, float, float] | None:
        chunks = [points for points, _pen in self.lines] + [triangles.reshape(-1, 2) for triangles, _pen in self.fills] \
            + [text.corners() for text in self.texts]
        if not chunks:
            return None
        every = np.concatenate(chunks)
        low, high = every.min(0), every.max(0)
        return float(low[0]), float(low[1]), float(high[0]), float(high[1])

    @property
    def warnings(self) -> list[str]:
        if not self.skipped:
            return []
        listed = ", ".join(f"{count} {kind}" for kind, count in sorted(self.skipped.items()))
        return [f"not drawn: {listed}"]


# --- the file's group codes ------------------------------------------------------------------------


def _pairs(path: Path) -> list[tuple[int, str]]:
    data = path.read_bytes()
    if data.startswith(b"AutoCAD Binary DXF"):
        raise DxfError(f"{path.name} is a binary DXF; the stills read ASCII DXF")
    text = data.decode("utf-8", errors="replace") if b"\xef\xbb\xbf" in data[:3] or _utf8(data) \
        else data.decode("cp1252", errors="replace")
    rows = text.splitlines()
    pairs = []
    for at in range(0, len(rows) - 1, 2):
        try:
            pairs.append((int(rows[at].strip()), rows[at + 1].strip()))
        except ValueError:
            raise DxfError(f"{path.name}: line {at + 1} is no group code ({rows[at].strip()[:20]!r})") from None
    return pairs


def _utf8(data: bytes) -> bool:
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


@dataclass
class Entity:
    kind: str
    codes: list[tuple[int, str]]
    vertices: list["Entity"] = field(default_factory=list)  # a POLYLINE's

    def get(self, code: int, default: Any = None) -> Any:
        for found, value in self.codes:
            if found == code:
                return value
        return default

    def number(self, code: int, default: float = 0.0) -> float:
        try:
            return float(self.get(code, default))
        except (TypeError, ValueError):
            return default

    def all(self, code: int) -> list[str]:
        return [value for found, value in self.codes if found == code]


def _records(pairs: list[tuple[int, str]]) -> Iterator[Entity]:
    """Each record that a code 0 opens, its codes after; a POLYLINE gathers its VERTEX records, an
    INSERT its ATTRIB records."""
    current: Entity | None = None
    polyline: Entity | None = None
    for code, value in pairs:
        if code == 0:
            if current is not None:
                if polyline is not None and current.kind in ("VERTEX", "ATTRIB"):
                    polyline.vertices.append(current)
                elif current.kind == "SEQEND" and polyline is not None:
                    yield polyline
                    polyline = None
                elif current.kind == "POLYLINE" or (current.kind == "INSERT" and int(current.number(66, 0)) == 1):
                    if polyline is not None:
                        yield polyline
                    polyline = current
                else:
                    if polyline is not None:
                        yield polyline
                        polyline = None
                    yield current
            current = Entity(value.upper(), [])
        elif current is not None:
            current.codes.append((code, value))
    if polyline is not None:
        yield polyline
    if current is not None and current.kind not in ("EOF", "SEQEND"):
        yield current


def _sections(pairs: list[tuple[int, str]]) -> dict[str, list[tuple[int, str]]]:
    sections: dict[str, list[tuple[int, str]]] = {}
    at = 0
    while at < len(pairs):
        if pairs[at] == (0, "SECTION") and at + 1 < len(pairs) and pairs[at + 1][0] == 2:
            name, start = pairs[at + 1][1].upper(), at + 2
            end = start
            while end < len(pairs) and pairs[end] != (0, "ENDSEC"):
                end += 1
            sections[name] = pairs[start:end]
            at = end
        at += 1
    return sections


# --- pens and geometry ----------------------------------------------------------------------------------


def _hex(rgb: int) -> str:
    return f"#{rgb & 0xFFFFFF:06x}"


def _aci(index: int) -> str | None:
    if index == DEFAULT_PEN or not 0 < index < 256:
        return None
    return "#" + ACI[3 * index:3 * index + 3].hex()


def _arc(cx: float, cy: float, radius: float, start: float, sweep: float) -> np.ndarray:
    count = max(MINIMUM, math.ceil(abs(sweep) / (2 * math.pi) * SEGMENTS))
    angles = start + np.linspace(0.0, sweep, count + 1)
    return np.stack([cx + radius * np.cos(angles), cy + radius * np.sin(angles)], 1)


def _bulged(points: list[tuple[float, float]], bulges: list[float], closed: bool) -> np.ndarray:
    """A polyline's points, each segment with a bulge made the arc it describes (tan(angle / 4))."""
    found = [np.array([points[0]])]
    count = len(points)
    for at in range(count if closed else count - 1):
        start, end = np.array(points[at]), np.array(points[(at + 1) % count])
        bulge = bulges[at] if at < len(bulges) else 0.0
        if abs(bulge) < 1e-12 or np.allclose(start, end):
            found.append(end[None])
            continue
        sweep = 4 * math.atan(bulge)
        chord = float(np.linalg.norm(end - start))
        radius = chord / (2 * math.sin(abs(sweep) / 2))
        middle = (start + end) / 2
        normal = np.array([-(end - start)[1], (end - start)[0]]) / chord
        offset = radius * math.cos(abs(sweep) / 2) * (1 if bulge > 0 else -1)
        centre = middle + normal * offset
        first = math.atan2(start[1] - centre[1], start[0] - centre[0])
        found.append(_arc(centre[0], centre[1], radius, first, sweep)[1:])
    return np.concatenate(found)


def _spline(entity: Entity) -> np.ndarray | None:
    """The kernel's B-spline of the entity's control points, knots and weights, sampled; else the
    cubic through its fit points (``_interpolated``)."""
    controls = list(zip(map(float, entity.all(10)), map(float, entity.all(20))))
    fits = list(zip(map(float, entity.all(11)), map(float, entity.all(21))))
    degree = int(entity.number(71, 3))
    knots = [float(value) for value in entity.all(40)]
    weights = [float(value) for value in entity.all(41)]
    if len(controls) >= 2 and len(knots) == len(controls) + degree + 1:
        from OCP.Geom import Geom_BSplineCurve
        from OCP.TColgp import TColgp_Array1OfPnt
        from OCP.TColStd import TColStd_Array1OfInteger, TColStd_Array1OfReal
        from OCP.gp import gp_Pnt

        unique, mults = [], []
        for knot in knots:
            if unique and abs(knot - unique[-1]) < 1e-12:
                mults[-1] += 1
            else:
                unique.append(knot)
                mults.append(1)
        poles = TColgp_Array1OfPnt(1, len(controls))
        for at, (x, y) in enumerate(controls, 1):
            poles.SetValue(at, gp_Pnt(x, y, 0.0))
        knot_array, mult_array = TColStd_Array1OfReal(1, len(unique)), TColStd_Array1OfInteger(1, len(mults))
        for at, (knot, mult) in enumerate(zip(unique, mults), 1):
            knot_array.SetValue(at, knot)
            mult_array.SetValue(at, mult)
        try:
            if len(weights) == len(controls) and any(abs(weight - 1) > 1e-12 for weight in weights):
                weight_array = TColStd_Array1OfReal(1, len(weights))
                for at, weight in enumerate(weights, 1):
                    weight_array.SetValue(at, weight)
                curve = Geom_BSplineCurve(poles, weight_array, knot_array, mult_array, degree)
            else:
                curve = Geom_BSplineCurve(poles, knot_array, mult_array, degree)
        except Exception:  # noqa: BLE001 - OCCT refuses a knot vector it cannot build; the control polygon stands in
            return np.array(controls)
        first, last = curve.FirstParameter(), curve.LastParameter()
        count = max(MINIMUM * 4, 16 * len(controls))
        return np.array([curve.Value(first + (last - first) * at / count).Coord()[:2] for at in range(count + 1)])
    if len(fits) >= 2:
        return _interpolated(entity, fits)
    return np.array(controls) if len(controls) >= 2 else None


def _interpolated(entity: Entity, fits: list[tuple[float, float]]) -> np.ndarray:
    """A spline of fit points alone, as CAD programs (and ezdxf, the viewer's reader) make it: the
    cubic through them at chord-length parameters (0 to 1), its second derivative zero at both
    ends -- or, where the entity gives end tangents, its first derivative there the tangent at
    the length of the fit polygon (``fit_points_to_cad_cv``); sampled."""
    points = np.array(fits, float)
    points = points[np.r_[True, np.linalg.norm(np.diff(points, axis=0), axis=1) > 0]]
    if len(points) < 3:
        return points
    chords = np.linalg.norm(np.diff(points, axis=0), axis=1)
    total = float(chords.sum())
    t = np.r_[0.0, np.cumsum(chords)] / total
    h = np.diff(t)
    n = len(points) - 1
    system = np.zeros((n + 1, n + 1))
    right = np.zeros((n + 1, 2))
    slopes = np.diff(points, axis=0) / h[:, None]
    for i in range(1, n):
        system[i, i - 1:i + 2] = (h[i - 1], 2 * (h[i - 1] + h[i]), h[i])
        right[i] = 6 * (slopes[i] - slopes[i - 1])
    tangents = None
    if entity.get(12) is not None and entity.get(13) is not None:
        start = np.array([entity.number(12), entity.number(22)])
        end = np.array([entity.number(13), entity.number(23)])
        if np.linalg.norm(start) > 0 and np.linalg.norm(end) > 0:
            tangents = (start / np.linalg.norm(start) * total, end / np.linalg.norm(end) * total)
    if tangents is None:  # natural: no bending at the ends
        system[0, 0] = system[n, n] = 1.0
    else:
        system[0, :2] = (2 * h[0], h[0])
        right[0] = 6 * (slopes[0] - tangents[0])
        system[n, n - 1:] = (h[n - 1], 2 * h[n - 1])
        right[n] = 6 * (tangents[1] - slopes[n - 1])
    bending = np.linalg.solve(system, right)
    found = [points[:1]]
    for i in range(n):
        share = np.linspace(0.0, 1.0, 17)[1:, None]
        a, b = 1 - share, share
        found.append(a * points[i] + b * points[i + 1]
                     + ((a ** 3 - a) * bending[i] + (b ** 3 - b) * bending[i + 1]) * h[i] ** 2 / 6)
    return np.concatenate(found)


def _triangulated(loops: list[np.ndarray]) -> np.ndarray | None:
    """Closed loops filled even-odd: the kernel's face of the largest loop with the rest as holes,
    meshed. (M, 3, 2) triangles."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Pnt

    def area(loop: np.ndarray) -> float:
        x, y = loop[:, 0], loop[:, 1]
        return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))

    def wire(loop: np.ndarray, outer: bool) -> Any:
        if (area(loop) > 0) != outer:
            loop = loop[::-1]
        polygon = BRepBuilderAPI_MakePolygon()
        for x, y in loop:
            polygon.Add(gp_Pnt(float(x), float(y), 0.0))
        polygon.Close()
        return polygon.Wire()

    loops = [loop[:-1] if len(loop) > 2 and np.allclose(loop[0], loop[-1]) else loop for loop in loops]
    loops = [loop for loop in loops if len(loop) >= 3 and abs(area(loop)) > 1e-12]
    if not loops:
        return None
    loops.sort(key=lambda loop: -abs(area(loop)))
    try:
        maker = BRepBuilderAPI_MakeFace(wire(loops[0], True), True)
        for hole in loops[1:]:
            maker.Add(wire(hole, False))
        face = maker.Face()
        span = float(np.ptp(np.concatenate(loops), 0).max()) or 1.0
        BRepMesh_IncrementalMesh(face, span * 1e-3, False, 0.5, False)
    except Exception:  # noqa: BLE001 - a boundary the kernel cannot face is left unfilled
        return None
    found = []
    explorer = TopExp_Explorer(face, TopAbs_FACE)
    while explorer.More():
        piece = TopoDS.Face_s(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(piece, location)
        if triangulation is not None:
            nodes = np.array([triangulation.Node(at).Coord()[:2] for at in range(1, triangulation.NbNodes() + 1)])
            corners = np.array([triangulation.Triangle(at).Get() for at in range(1, triangulation.NbTriangles() + 1)]) - 1
            if piece.Orientation() == TopAbs_REVERSED:
                corners = corners[:, [0, 2, 1]]
            found.append(nodes[corners])
        explorer.Next()
    return np.concatenate(found) if found else None


def _hatch_loops(entity: Entity) -> list[np.ndarray]:
    """A HATCH's boundary paths as closed point loops: polyline paths (with bulges) and edge paths
    of lines, arcs and ellipses (a spline edge by its control points)."""
    codes, loops, at = entity.codes, [], 0
    while at < len(codes) and codes[at][0] != 91:
        at += 1
    paths = int(float(codes[at][1])) if at < len(codes) else 0
    at += 1
    for _ in range(paths):
        while at < len(codes) and codes[at][0] != 92:
            at += 1
        if at >= len(codes):
            break
        flags = int(float(codes[at][1]))
        at += 1
        if flags & 2:  # a polyline path
            bulged, closed, count = 0, 1, 0
            points, bulges = [], []
            while at < len(codes) and codes[at][0] in (72, 73, 93):
                bulged = int(float(codes[at][1])) if codes[at][0] == 72 else bulged
                closed = int(float(codes[at][1])) if codes[at][0] == 73 else closed
                count = int(float(codes[at][1])) if codes[at][0] == 93 else count
                at += 1
            while len(points) < count and at < len(codes):
                if codes[at][0] == 10:
                    points.append((float(codes[at][1]), float(codes[at + 1][1])))
                    bulges.append(0.0)
                    at += 2
                elif codes[at][0] == 42 and bulged:
                    bulges[-1] = float(codes[at][1])
                    at += 1
                else:
                    at += 1
            if at < len(codes) and codes[at][0] == 42 and bulged:
                bulges[-1] = float(codes[at][1])
                at += 1
            if len(points) >= 2:
                loops.append(_bulged(points, bulges, True))
            continue
        while at < len(codes) and codes[at][0] != 93:
            at += 1
        edges = int(float(codes[at][1])) if at < len(codes) else 0
        at += 1
        pieces = []
        for _edge in range(edges):
            while at < len(codes) and codes[at][0] != 72:
                at += 1
            if at >= len(codes):
                break
            kind = int(float(codes[at][1]))
            at += 1
            values: dict[int, list[float]] = {}
            while at < len(codes) and codes[at][0] not in (72, 92, 97, 75, 76, 98):
                values.setdefault(codes[at][0], []).append(float(codes[at][1]) if codes[at][0] < 100 else 0.0)
                at += 1
            first = lambda code, default=0.0: values.get(code, [default])[0]  # noqa: E731
            if kind == 1:
                pieces.append(np.array([[first(10), first(20)], [first(11), first(21)]]))
            elif kind == 2:  # a clockwise arc's angles are given mirrored, as ezdxf reads them
                start, end = math.radians(first(50)), math.radians(first(51))
                sweep = (end - start) % (2 * math.pi) or 2 * math.pi
                ccw = first(73, 1.0) != 0
                pieces.append(_arc(first(10), first(20), first(40), start if ccw else -start, sweep if ccw else -sweep))
            elif kind == 3:
                centre, major = np.array([first(10), first(20)]), np.array([first(11), first(21)])
                ratio, start, end = first(40, 1.0), math.radians(first(50)), math.radians(first(51))
                sweep = (end - start) % (2 * math.pi) or 2 * math.pi
                pieces.append(_ellipse(centre, major, ratio, start, sweep * (1 if first(73, 1.0) != 0 else -1)))
            elif kind == 4:
                xs, ys = values.get(10, []), values.get(20, [])
                pieces.append(np.stack([xs, ys], 1) if xs else np.zeros((0, 2)))
        pieces = [piece for piece in pieces if len(piece)]
        if pieces:
            loops.append(np.concatenate(pieces))
    return loops


def _ellipse(centre: np.ndarray, major: np.ndarray, ratio: float, start: float, sweep: float) -> np.ndarray:
    count = max(MINIMUM, math.ceil(abs(sweep) / (2 * math.pi) * SEGMENTS))
    angles = start + np.linspace(0.0, sweep, count + 1)
    minor = np.array([-major[1], major[0]]) * ratio
    return centre + np.cos(angles)[:, None] * major + np.sin(angles)[:, None] * minor


# --- reading ----------------------------------------------------------------------------------------------


class _Reader:
    def __init__(self, path: Path) -> None:
        self.path = path
        pairs = _pairs(path)
        sections = _sections(pairs)
        if "ENTITIES" not in sections:
            raise DxfError(f"{path.name} has no ENTITIES section: it does not read as a DXF")
        self.layers: dict[str, tuple[str | None, bool]] = {}  # name: its pen, whether it draws
        for record in _records(sections.get("TABLES", [])):
            if record.kind == "LAYER":
                name = str(record.get(2, "")).strip()
                colour = int(record.number(62, DEFAULT_PEN))
                frozen = int(record.number(70, 0)) & 1
                true = record.get(420)
                pen = _hex(int(true)) if true is not None else _aci(abs(colour))
                self.layers[name.upper()] = (pen, colour >= 0 and not frozen)
        self.blocks: dict[str, tuple[np.ndarray, list[Entity]]] = {}
        name, base, members = None, np.zeros(2), []
        for record in _records(sections.get("BLOCKS", [])):
            if record.kind == "BLOCK":
                name, base, members = str(record.get(2, "")), np.array([record.number(10), record.number(20)]), []
            elif record.kind == "ENDBLK":
                if name is not None:
                    self.blocks[name.upper()] = (base, members)
                name = None
            elif name is not None:
                members.append(record)
        self.drawing = Drawing(path, layers=len(self.layers), files=files_of([path]))
        self.expanded = 0  # the entities drawn so far, a block's members once per place they are drawn
        for record in _records(sections["ENTITIES"]):
            if int(record.number(67, 0)) == 1:  # paper space
                continue
            self.drawing.entities += 1
            self.entity(record, np.eye(3), None, "0", 0)

    def pen(self, entity: Entity, block_pen: str | None, block_layer: str) -> tuple[str | None, bool]:
        layer = str(entity.get(8, "0")).strip()
        if layer == "0" and block_layer != "0":
            layer = block_layer  # an entity of a block on layer 0 takes its insert's layer
        layer_pen, shown = self.layers.get(layer.upper(), (None, True))
        true = entity.get(420)
        if true is not None:
            return _hex(int(true)), shown
        colour = int(entity.number(62, 256))
        if colour == 0:
            return block_pen, shown
        if colour == 256:
            return layer_pen, shown
        return _aci(abs(colour)), shown

    def room(self, count: float) -> None:
        """Refuse the drawing if ``count`` more entities would take it past ``MAX_EXPANDED``."""
        if not self.expanded + count <= MAX_EXPANDED:  # a NaN or infinite count is past it too
            raise DxfError(f"{self.drawing.path.name}: its blocks draw more than {MAX_EXPANDED:,} entities")

    def entity(self, entity: Entity, transform: np.ndarray, block_pen: str | None, block_layer: str, depth: int) -> None:
        kind = entity.kind
        self.room(1)
        self.expanded += 1
        if kind not in DRAWN:
            self.drawing.skipped[kind] += 1
            return
        pen, shown = self.pen(entity, block_pen, block_layer)
        if not shown:
            return
        mirror = np.diag([-1.0, 1.0, 1.0]) if entity.number(230, 1.0) < 0 else np.eye(3)
        place = transform @ mirror

        def line(points: np.ndarray) -> None:
            points = np.asarray(points, float)
            if len(points) >= 2:
                self.drawing.lines.append((points @ place[:2, :2].T + place[:2, 2], pen))

        if kind == "LINE":
            line(np.array([[entity.number(10), entity.number(20)], [entity.number(11), entity.number(21)]]))
        elif kind in ("RAY", "XLINE"):
            self.drawing.skipped[kind] += 1
        elif kind == "CIRCLE":
            line(_arc(entity.number(10), entity.number(20), entity.number(40), 0.0, 2 * math.pi))
        elif kind == "ARC":
            start, end = math.radians(entity.number(50)), math.radians(entity.number(51))
            sweep = (end - start) % (2 * math.pi) or 2 * math.pi
            line(_arc(entity.number(10), entity.number(20), entity.number(40), start, sweep))
        elif kind == "ELLIPSE":
            start, end = entity.number(41, 0.0), entity.number(42, 2 * math.pi)
            sweep = (end - start) % (2 * math.pi) or 2 * math.pi
            line(_ellipse(np.array([entity.number(10), entity.number(20)]), np.array([entity.number(11), entity.number(21)]),
                          entity.number(40, 1.0), start, sweep))
        elif kind == "LWPOLYLINE":
            points, bulges = [], []
            for code, value in entity.codes:
                if code == 10:
                    points.append([float(value), 0.0])
                    bulges.append(0.0)
                elif code == 20 and points:
                    points[-1][1] = float(value)
                elif code == 42 and bulges:
                    bulges[-1] = float(value)
            if len(points) >= 2:
                line(_bulged([tuple(point) for point in points], bulges, bool(int(entity.number(70, 0)) & 1)))
        elif kind == "POLYLINE":
            flags = int(entity.number(70, 0))
            if flags & (16 | 64):  # a polygon or polyface mesh: 3D
                self.drawing.skipped["POLYLINE mesh"] += 1
                return
            points = [(vertex.number(10), vertex.number(20)) for vertex in entity.vertices]
            bulges = [vertex.number(42, 0.0) for vertex in entity.vertices]
            if len(points) >= 2:
                line(_bulged(points, bulges, bool(flags & 1)))
        elif kind == "SPLINE":
            found = _spline(entity)
            if found is not None:
                line(found)
        elif kind == "LEADER":
            line(np.stack([[float(value) for value in entity.all(10)], [float(value) for value in entity.all(20)]], 1))
        elif kind in ("SOLID", "TRACE"):
            corners = [(entity.number(10 + at), entity.number(20 + at)) for at in range(4)]
            if entity.get(13) is None:
                corners[3] = corners[2]
            a, b, c, d = (np.array(corner) for corner in corners)
            triangles = np.array([[a, b, c], [b, d, c]]) if not np.allclose(c, d) else np.array([[a, b, c]])
            triangles = triangles @ place[:2, :2].T + place[:2, 2]
            self.drawing.fills.append((triangles, pen))
        elif kind == "HATCH":
            if not int(entity.number(70, 0)) & 1:
                self.drawing.skipped["HATCH pattern"] += 1
                for loop in _hatch_loops(entity):
                    line(np.vstack([loop, loop[:1]]))
                return
            triangles = _triangulated(_hatch_loops(entity))
            if triangles is not None:
                self.drawing.fills.append((triangles @ place[:2, :2].T + place[:2, 2], pen))
        elif kind in ("TEXT", "ATTRIB", "MTEXT"):
            if kind == "ATTRIB" and int(entity.number(70, 0)) & 1:  # an invisible attribute
                return
            self.text(entity, place, pen)
        elif kind in ("INSERT", "DIMENSION"):
            name = str(entity.get(2, "")).strip()
            block = self.blocks.get(name.upper())
            if block is None or depth > MAX_BLOCK_DEPTH:
                self.drawing.skipped[kind] += block is None
                return
            base, members = block
            layer = str(entity.get(8, "0")).strip()
            layer = layer if layer != "0" else block_layer
            if kind == "DIMENSION":  # a dimension's block is drawn where it stands
                placements = [transform]
            else:  # an insert (and a MINSERT's grid, spaced along the insert's own axes)
                angle = math.radians(entity.number(50, 0.0))
                c, s = math.cos(angle), math.sin(angle)
                turned = place @ np.array([[c, -s, entity.number(10)], [s, c, entity.number(20)], [0, 0, 1]])
                scaled = np.diag([entity.number(41, 1.0), entity.number(42, 1.0), 1.0]) \
                    @ np.array([[1, 0, -base[0]], [0, 1, -base[1]], [0, 0, 1]])
                columns, rows = max(entity.number(70, 1), 1.0), max(entity.number(71, 1), 1.0)
                self.room(columns * rows * max(len(members), 1))  # every cell of the grid draws the block
                placements = []
                for column in range(int(columns)):
                    for row in range(int(rows)):
                        shift = np.eye(3)
                        shift[:2, 2] = (column * entity.number(44, 0.0), row * entity.number(45, 0.0))
                        placements.append(turned @ shift @ scaled)
            for inner in placements:
                for member in members:
                    self.entity(member, inner, pen, layer, depth + 1)
            for attribute in entity.vertices:  # an insert's attributes stand where they are written
                self.entity(attribute, transform, pen, block_layer, depth + 1)

    def text(self, entity: Entity, place: np.ndarray, pen: str | None) -> None:
        """TEXT, ATTRIB or MTEXT laid out: each line's baseline start, by its alignment."""
        height = entity.number(40, 1.0)
        if entity.kind == "MTEXT":
            lines = _paragraphs("".join(entity.all(3)) + str(entity.get(1, "")))
            if entity.get(11) is not None:
                angle = math.atan2(entity.number(21), entity.number(11))
            else:
                angle = entity.number(50, 0.0)  # MTEXT's rotation is in radians
            attach = int(entity.number(71, 1)) or 1
            horizontal, vertical = (attach - 1) % 3, (attach - 1) // 3  # 0 left/top, 1 centre/middle, 2 right/bottom
            pitch = LINE_SPACING * height * entity.number(44, 1.0)
            reference = np.array([entity.number(10), entity.number(20)])
            block = height + pitch * (len(lines) - 1)
            first = {0: -height, 1: -height + block / 2, 2: -height + block}[vertical]  # the first baseline's rise
            width = 1.0
        else:
            lines = [_words(str(entity.get(1, "")))]
            angle = math.radians(entity.number(50, 0.0))
            width = entity.number(41, 1.0) or 1.0
            align_h, align_v = int(entity.number(72, 0)), int(entity.number(73, 0))
            aligned = align_h or align_v
            reference = np.array([entity.number(11), entity.number(21)]) if aligned and entity.get(11) is not None \
                else np.array([entity.number(10), entity.number(20)])
            if align_h in (3, 5) and entity.get(11) is not None:  # aligned or fit: from the first point to the second
                start, end = np.array([entity.number(10), entity.number(20)]), np.array([entity.number(11), entity.number(21)])
                angle = math.atan2(*(end - start)[::-1])
                span = float(np.linalg.norm(end - start))
                natural = measure(lines[0], height) or 1.0
                if align_h == 3:
                    height *= span / natural
                else:
                    width = span / natural
                reference, align_h, align_v = start, 0, 0
            if align_h == 4:  # middle: centred both ways
                align_h, align_v = 1, 2
            horizontal = {0: 0, 1: 1, 2: 2}.get(align_h, 0)
            first = {0: 0.0, 1: 0.25 * height, 2: -height / 2, 3: -height}.get(align_v, 0.0)
            pitch = 0.0
        if not any(line.strip() for line in lines):
            return
        direction = np.array([math.cos(angle), math.sin(angle)])
        up = np.array([-direction[1], direction[0]])
        starts = []
        for index, line in enumerate(lines):
            length = measure(line, height) * width
            shift = {0: 0.0, 1: -length / 2, 2: -length}[horizontal]
            starts.append(reference + direction * shift + up * (first - index * pitch))
        # Into the drawing: the placement's turn and scale on the words, its move on their starts.
        moved = [tuple(place[:2, :2] @ start + place[:2, 2]) for start in starts]
        turned = place[:2, :2] @ direction
        scale = float(np.linalg.norm(turned)) or 1.0
        stretch = float(np.linalg.norm(place[:2, :2] @ up)) or 1.0
        self.drawing.texts.append(Text(lines, moved, tuple(turned / scale), height * stretch, width * scale / stretch,
                                       pen))


def read_dxf(path: Path) -> Drawing:
    """The DXF at ``path``, flattened (see the module docstring)."""
    return _Reader(Path(path)).drawing
