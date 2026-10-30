"""PROTOTYPE: what the snapshot page paints over its finished picture, painted the same way over
OCCT's: Measure's dimensions.

The page draws each measurement on a 2D canvas over the WebGL picture (``renderMeshScene.js``
``measurementsOverlay``), in the output's pixels at ``height / 900`` of a viewer's
(``ANNOTATION_REFERENCE_HEIGHT_PX``), with the viewer's own code: ``screenSpaceDimensionLayout``
(witness lines from the two ends, the dimension line 24 px off them, arrowheads, the label at its
middle) and ``drawMeasurementMark`` (active: lines 2.6 and 1.6 px, rings of 4 px radius filled
white with a 2 px stroke, the label ``600 8px`` system face, white, on a 92% slate chip, rounded
5 px, stroked 1 px in the mark's colour, kept 4 px inside the frame). So here: the same layout in
the same units, each piece's coverage computed exactly (a capsule for a round-capped line, a disc,
a ring, a triangle, a rounded box, the label's words from ``text.py``) on a 4 x 4 supersampled grid
and laid over the frame source-over, one after another, in sRGB, as a canvas composites.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

REFERENCE_HEIGHT = 900
SUPERSAMPLE = 4
LABEL_BACKGROUND = (15, 23, 42, 0.92)
OFFSET, OVERSHOOT, ARROW_LENGTH, ARROW_WIDTH = 24.0, 5.0, 8.0, 3.5
LINE, WITNESS, RING, RING_STROKE = 2.6, 1.6, 4.0, 2.0
LABEL_PADDING_X, LABEL_PADDING_Y, LABEL_MARGIN, LABEL_RADIUS = 6.0, 3.0, 4.0, 5.0
LABEL_FACE = (600, 8)  # MEASURE_DIMENSION_LABEL_FONT: 600 8px, the UI face


def layout(start: tuple[float, float], end: tuple[float, float]) -> dict[str, Any] | None:
    """``screenSpaceDimensionLayout``: the two ends on the screen to rings, witnesses, the offset
    dimension line, its arrowheads and the label's point, in the same (viewer) pixels."""
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    if not length > 1e-6:
        return None
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    reach = OFFSET + OVERSHOOT
    witnesses = [(start, (start[0] + px * reach, start[1] + py * reach)), (end, (end[0] + px * reach, end[1] + py * reach))]
    a = (start[0] + px * OFFSET, start[1] + py * OFFSET)
    b = (end[0] + px * OFFSET, end[1] + py * OFFSET)
    flip = length < ARROW_LENGTH * 2.5
    arrows = []
    for tip, way in ((a, -1 if flip else 1), (b, 1 if flip else -1)):
        base = (tip[0] + ux * ARROW_LENGTH * way, tip[1] + uy * ARROW_LENGTH * way)
        arrows.append((tip, (base[0] + px * ARROW_WIDTH, base[1] + py * ARROW_WIDTH),
                       (base[0] - px * ARROW_WIDTH, base[1] - py * ARROW_WIDTH)))
    return {"rings": [start, end], "witnesses": witnesses, "line": (a, b), "arrows": arrows,
            "label": ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)}


class Painter:
    """Source-over painting onto an sRGB frame (bytes, (h, w, 3), in place), each piece's
    coverage taken on a supersampled grid over its own box, in viewer pixels times ``scale``, and
    the frame kept in bytes after every piece, as a canvas keeps its pixels."""

    def __init__(self, frame: np.ndarray, scale: float) -> None:
        self.frame = frame
        self.scale = scale
        self.height, self.width = frame.shape[:2]

    def _grid(self, box: tuple[float, float, float, float]) -> tuple[Any, np.ndarray, np.ndarray] | None:
        x0, y0 = max(int(math.floor(box[0])), 0), max(int(math.floor(box[1])), 0)
        x1, y1 = min(int(math.ceil(box[2])), self.width), min(int(math.ceil(box[3])), self.height)
        if x1 <= x0 or y1 <= y0:
            return None
        s = SUPERSAMPLE
        xs = x0 + (np.arange((x1 - x0) * s) + 0.5) / s
        ys = y0 + (np.arange((y1 - y0) * s) + 0.5) / s
        return (slice(y0, y1), slice(x0, x1)), xs[None, :], ys[:, None]

    def _over(self, where: Any, inside: np.ndarray, color: tuple[float, float, float], alpha: float = 1.0) -> None:
        s = SUPERSAMPLE
        h, w = inside.shape[0] // s, inside.shape[1] // s
        self.coverage(where, inside.reshape(h, s, w, s).mean(axis=(1, 3)), color, alpha)

    def coverage(self, where: Any, cover: np.ndarray, color: tuple[float, float, float], alpha: float = 1.0) -> None:
        patch = self.frame[where].astype(np.float64)
        a = cover[..., None] * alpha
        self.frame[where] = np.rint(np.asarray(color, float) * a + patch * (1 - a)).astype(np.uint8)

    def line(self, a: tuple[float, float], b: tuple[float, float], width: float, color: Any, alpha: float = 1.0) -> None:
        """A round-capped segment ``width`` viewer pixels wide (a capsule): sampled only on the
        pixels whose centre is within reach of it, not over its whole box (a long diagonal's box
        is mostly empty)."""
        k = self.scale
        a, b, half = (a[0] * k, a[1] * k), (b[0] * k, b[1] * k), width * k / 2
        x0, y0 = max(int(math.floor(min(a[0], b[0]) - half - 1)), 0), max(int(math.floor(min(a[1], b[1]) - half - 1)), 0)
        x1 = min(int(math.ceil(max(a[0], b[0]) + half + 1)), self.width)
        y1 = min(int(math.ceil(max(a[1], b[1]) + half + 1)), self.height)
        if x1 <= x0 or y1 <= y0:
            return
        dx, dy = b[0] - a[0], b[1] - a[1]
        span = dx * dx + dy * dy or 1.0

        def distance(xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
            t = np.clip(((xs - a[0]) * dx + (ys - a[1]) * dy) / span, 0, 1)
            return np.hypot(xs - (a[0] + t * dx), ys - (a[1] + t * dy))

        # The pixels whose centre is within reach of the line, row by row: an interval of each.
        length = math.sqrt(span)
        nx, ny = -dy / length, dx / length
        reach = half + 0.75  # a pixel's corner is 0.71 from its centre
        rows = np.arange(y0, y1)
        if abs(nx) > 1e-9:
            offset = ny * (rows + 0.5 - a[1])
            lo = a[0] + (-reach - offset) / nx - 0.5
            hi = a[0] + (reach - offset) / nx - 0.5
            lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
            starts = np.clip(np.floor(lo).astype(int), x0, x1)
            stops = np.clip(np.ceil(hi).astype(int) + 1, x0, x1)
        else:
            inside_rows = np.abs(ny * (rows + 0.5 - a[1])) <= reach
            starts = np.where(inside_rows, x0, x1)
            stops = np.full_like(starts, x1)
        counts = np.maximum(stops - starts, 0)
        if not counts.sum():
            return
        ys = np.repeat(rows, counts)
        xs = np.concatenate([np.arange(start, stop) for start, stop in zip(starts, stops) if stop > start])
        near = distance(xs + 0.5, ys + 0.5) <= reach
        ys, xs = ys[near], xs[near]
        if not len(xs):
            return
        s = SUPERSAMPLE
        offsets = (np.arange(s) + 0.5) / s
        sx = (xs[:, None, None] + offsets[None, None, :]).repeat(s, 1)
        sy = (ys[:, None, None] + offsets[None, :, None]).repeat(s, 2)
        cover = (distance(sx, sy) <= half).mean(axis=(1, 2))
        patch = self.frame[ys, xs].astype(np.float64)
        weight = cover[:, None] * alpha
        self.frame[ys, xs] = np.rint(np.asarray(color, float) * weight + patch * (1 - weight)).astype(np.uint8)

    def triangle(self, p: Any, q: Any, r: Any, color: Any, alpha: float = 1.0) -> None:
        k = self.scale
        p, q, r = [(v[0] * k, v[1] * k) for v in (p, q, r)]
        grid = self._grid((min(p[0], q[0], r[0]) - 1, min(p[1], q[1], r[1]) - 1, max(p[0], q[0], r[0]) + 1,
                           max(p[1], q[1], r[1]) + 1))
        if grid is None:
            return
        where, xs, ys = grid

        def side(u: Any, v: Any) -> np.ndarray:
            return (v[0] - u[0]) * (ys - u[1]) - (v[1] - u[1]) * (xs - u[0])

        s1, s2, s3 = side(p, q), side(q, r), side(r, p)
        inside = ((s1 >= 0) & (s2 >= 0) & (s3 >= 0)) | ((s1 <= 0) & (s2 <= 0) & (s3 <= 0))
        self._over(where, inside, color, alpha)

    def disc(self, centre: Any, radius: float, color: Any, ring: float = 0.0, alpha: float = 1.0) -> None:
        """A filled disc of ``radius``, or (``ring`` > 0) the stroke of that width round it."""
        k = self.scale
        c, r, half = (centre[0] * k, centre[1] * k), radius * k, ring * k / 2
        outer = r + half if ring else r
        grid = self._grid((c[0] - outer - 1, c[1] - outer - 1, c[0] + outer + 1, c[1] + outer + 1))
        if grid is None:
            return
        where, xs, ys = grid
        d = np.hypot(xs - c[0], ys - c[1])
        inside = (np.abs(d - r) <= half) if ring else (d <= r)
        self._over(where, inside, color, alpha)

    def rounded_box(self, x: float, y: float, w: float, h: float, radius: float, color: Any, alpha: float = 1.0,
                    stroke: float = 0.0) -> None:
        """A rounded rectangle filled, or (``stroke`` > 0) its outline stroked that wide."""
        k = self.scale
        x, y, w, h, radius, half = x * k, y * k, w * k, h * k, radius * k, stroke * k / 2
        grid = self._grid((x - half - 1, y - half - 1, x + w + half + 1, y + h + half + 1))
        if grid is None:
            return
        where, xs, ys = grid
        # signed distance to the rounded rectangle
        cx, cy = x + w / 2, y + h / 2
        qx, qy = np.abs(xs - cx) - (w / 2 - radius), np.abs(ys - cy) - (h / 2 - radius)
        outside = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - radius
        inside = (np.abs(outside) <= half) if stroke else (outside <= 0)
        self._over(where, inside, color, alpha)

    def words(self, text: str, face: Any, x: float, middle: float, color: Any, align: str = "left") -> None:
        """Words in ``face`` (``text.face``) with their em box's middle on ``middle`` (``textBaseline``
        "middle"), from ``x`` (``align`` "center": centred on it), in viewer pixels."""
        from cadgen.engine.render.text import coverage

        k = self.scale
        left, top = x * k, middle * k - face.size * k / 2  # the em box is the font size tall
        width = face.width(text) * k
        start = left - width / 2 if align == "center" else left
        box = (int(max(math.floor(start - 2), 0)), int(max(math.floor(top - 4), 0)))
        size = (min(int(math.ceil(width)) + 5, self.width - box[0]),
                min(int(math.ceil(face.size * k)) + 9, self.height - box[1]))
        if size[0] <= 0 or size[1] <= 0:
            return
        cover = coverage([text], face, size, (left - box[0], top - box[1]), 0, scale=k, align=align)
        self.coverage((slice(box[1], box[1] + size[1]), slice(box[0], box[0] + size[0])), cover, color)


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def paint_measurements(frame: np.ndarray, marks: list[dict[str, Any]], project: Any) -> None:
    """Measure's marks painted over ``frame`` (sRGB bytes, (h, w, 3), changed in place) as the
    snapshot page paints them: ``project`` maps world points to output pixels (x right, y down)."""
    from cadgen.engine.render.text import face as text_face

    height, width = frame.shape[:2]
    scale = height / REFERENCE_HEIGHT
    painter = Painter(frame, scale)
    bounds = (width / scale, height / scale)
    for mark in marks:
        ends = project(np.array([mark["start"], mark["end"]], float))
        found = layout(tuple(ends[0] / scale), tuple(ends[1] / scale))
        if found is None:
            continue
        color = _rgb(mark["color"])
        for a, b in found["witnesses"]:
            painter.line(a, b, WITNESS, color)
        painter.line(*found["line"], LINE, color)
        for arrow in found["arrows"]:
            painter.triangle(*arrow, color)
        for point in found["rings"]:
            painter.disc(point, RING, (255, 255, 255))
            painter.disc(point, RING, color, ring=RING_STROKE)
        label = str(mark.get("label") or "").strip()
        if not label:
            continue
        face = text_face(*LABEL_FACE)
        chip_w, chip_h = face.width(label) + LABEL_PADDING_X * 2, 11 + LABEL_PADDING_Y * 2
        x = min(max(found["label"][0] - chip_w / 2, LABEL_MARGIN), max(LABEL_MARGIN, bounds[0] - chip_w - LABEL_MARGIN))
        y = min(max(found["label"][1] - chip_h / 2, LABEL_MARGIN), max(LABEL_MARGIN, bounds[1] - chip_h - LABEL_MARGIN))
        painter.rounded_box(x, y, chip_w, chip_h, LABEL_RADIUS, LABEL_BACKGROUND[:3], LABEL_BACKGROUND[3])
        painter.rounded_box(x, y, chip_w, chip_h, LABEL_RADIUS, color, stroke=1.0)
        # textBaseline "middle": the em box's middle on the chip's; textAlign "center".
        painter.words(label, face, x + chip_w / 2, y + chip_h / 2, (255, 255, 255), align="center")
