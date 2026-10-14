"""An independent machine-crash checker for posted CAM programs (test support, not the engine).

:func:`check` reads one setup's posted program (a list of texts when a post writes one file per tool) with
:mod:`gcode_reader`, runs it the way a controller would (modal G0/G1/G2/G3, G17-19, G43/G49 tool length, G53
machine moves, G28/G30 homes, canned cycles with their R plane and initial level, spindle state and direction, rotary
A/B/C, tool centre point G43.4/G234, tilted planes G68.2/G53.1 and G254, a lathe's diameter mode, the beam of a
cutting machine, the wire of a wire EDM) against its own model of the material, and returns a :class:`Finding` for
everything that would crash the machine or break the tool. It never reads the engine's toolpath, simulation or
checks: only the posted text, the stock, the tools and the setup's heights.

The material: a mill keeps a Z height map of the stock in the setup's WCS (an oriented box or a cylinder, so a 3+2
setup's tilted stock is exact), lowered by every feed move with the tool's own bottom profile (flat, ball, bull,
cone); a tool tilted under TCP lowers it along its axis, never by more than its axis points (conservative). A 4th
axis wrap keeps the bar's radius over (X, angle) instead; a lathe keeps the bar's outer and bore radius over Z. A
rapid is a crash where the tool's lower surface comes more than ``tol_mm`` under the material left there. Slivers a
lathe's passes leave between them thinner than ``2 * lathe_sliver_mm`` count as cut.

The rules (``Finding.rule``):

``rapid_into_stock``  a rapid's tool passes through material not cut yet (rule 1)
``table``             a move takes the tip more than ``below_bottom_mm`` (plus a drill's point, a tap's lead) under
                      the stock's bottom: into the table, the vise or the parallels
``fixture``           a move takes the tool (tip to stickout) into a fixture keep-out
``holder``            the shank (above the flutes) or the holder (above the stickout) runs into the material
``spindle_off``       a cutting move on a spindle machine with the spindle stopped (rule 2)
``spinup``            GRBL: a cutting move right after a spindle start with no dwell for it to reach speed
``tool_change``       a tool change away from the machine's top (mill ``M6`` without ``G53 Z0``/``G28 Z0``, or on
                      Mach3 below the program's clearance; a lathe
                      index away from ``G28 U0 W0``/``G30``), or a second tool in one GRBL file (rule 3)
``entry``             the first motion of a program or after a tool change is not Z up to a safe height, then X Y,
                      then Z down (rotary axes first on a 5-axis) (rule 4)
``length``            a mill's Z moves after a tool change before its tool length (G43 H, G43.4, G234), or the H
                      is another tool's
``modal``             a move before G21, G90 or a work offset, a G20, or a move left in incremental mode
``rotary``            a rotary axis turns with the tool below the clearance height (no TCP), straight out of a cut
                      below the retract height (TCP), or turns while cutting without TCP (rule 5)
``tap``               a tap fed in with the spindle the wrong way, out without reversing, out at rapid, at a feed
                      that is not rpm x pitch, into material no drill removed, or a Fanuc G84 without M29 (rule 6)
``arc``               an arc whose end is off its circle, or a degenerate (zero-size) one (rule 7)
``travel``            the program spans more than the machine's travel, or a rotary axis leaves its limits (rule 8)
``beam``              a beam on during a rapid, fired at the cut height, without a pierce dwell, or a torch that
                      rapids low (rule 9)
``wire``              a wire EDM rapid across solid with the wire threaded (rule 10)

What it cannot see, and what it lets pass on purpose, is :data:`LIMITS`. :func:`context_from_cam` builds a setup's
context from a plan's result GLB extras; :func:`check_plan` checks every posted file of a ``cam.plan`` result.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

from tests.python.support import gcode_reader

__all__ = ["LIMITS", "Finding", "StockShape", "ToolShape", "check", "check_plan", "context_from_cam"]

#: What the checker does not model, and what it lets pass on purpose.
LIMITS = (
    "The part is not known: material is the stock minus what the program cut, so a feed move that gouges the part "
    "is not a finding (the engine's gouge check owns it); a rapid through the part is, since the part is uncut stock.",
    "Each setup starts from the whole stock: what an earlier setup removed is not credited (conservative).",
    "A through hole or profile may take the tip 1 mm plus the tool's point (a drill's cone, a tap's three pitches "
    "of lead) under the stock's bottom: the stock must sit on parallels or a spoilboard clear of it there.",
    "The shank and holder are checked only where the job gives the flute length, stickout and holder diameter; the "
    "spindle nose above the holder, the head, the table, a trunnion and a turret are not modelled.",
    "A tool tilted under TCP cuts the height map only along its axis points (less than it does: conservative); its "
    "axis follows the documented A/C (B/C) table convention, so a machine turning the other way is not seen.",
    "A lathe tool is a point (a drill a disc of its radius): a holder, a grooving blade's width and a boring bar's "
    "body are not checked, and slivers up to 1 mm thick between passes count as cut.",
    "A rapid may graze material by up to tol_mm (0.05 mm) deep and 0.02 mm in from the tool's side (sampling).",
    "A wire EDM's slug is not modelled: a threaded rapid is clear only along a cut kerf or in a start hole.",
)

TOP = math.inf
SPINDLE_KINDS = ("mill", "mill4", "mill5", "router", "lathe")
MILL_KINDS = ("mill", "mill4", "mill5", "router")
BEAM_KINDS = ("laser", "plasma", "waterjet")


@dataclass(frozen=True)
class Finding:
    rule: str
    file: int
    line: int
    message: str

    def __str__(self) -> str:
        return f"[{self.rule}] file {self.file + 1} line {self.line}: {self.message}"


# --- tools ---------------------------------------------------------------------------------------------------

#: Tools whose end is a cone (a tap is modelled with a drill's 118° point over its minor radius).
_CONES = ("vee", "chamfer", "engraver", "spot", "drill", "tap")


@dataclass(frozen=True)
class ToolShape:
    """A cutting end: its radius and the height of its lower surface above the tip at a distance from its axis; the
    shank above the flutes and the holder above the stickout."""

    number: int
    type: str = "flat"
    radius: float = 0.0
    corner_radius: float = 0.0
    half_angle_deg: float = 45.0
    tip_radius: float = 0.0
    length: float = 0.0
    pitch: float = 0.0
    hand: str = "right"
    family: str = "mill"
    #: The shank's radius from ``length`` (the flutes' top) to ``stickout``; the holder's radius and length above.
    shank_radius: float = 0.0
    stickout: float = 0.0
    holder_radius: float = 0.0
    holder_length: float = 0.0
    #: The flutes' length was given (else ``length`` is a guess and the shank is not checked).
    flutes_known: bool = False

    @classmethod
    def from_job(cls, entry: dict, position: int = 0) -> "ToolShape":
        kind = entry.get("type", "flat")
        number = entry.get("number")
        if number is None:
            digits = re.sub(r"\D", "", str(entry.get("id", "")))
            number = int(digits) if digits else position + 1
        angle = entry.get("angle_deg") or (entry.get("point_angle", 118.0) if kind in ("drill", "tap") else 90.0)
        if kind == "tap":
            angle = 118.0
        family = ("lathe" if kind in ("turn", "groove", "thread", "partoff") else
                  "cutting" if kind in ("beam", "wire") else "mill")
        radius = float(entry.get("diameter_mm") or 0.0) / 2.0
        if kind == "beam":
            radius = float(entry.get("kerf_mm") or 0.0) / 2.0
        if kind == "tap":
            radius = max(0.0, radius - float(entry.get("pitch_mm") or 0.0) / 2.0)   # the minor radius
        flutes = float(entry.get("flute_length_mm") or 0.0)
        length = flutes or 3.0 * 2.0 * radius
        shank = float(entry.get("shank_diameter_mm") or entry.get("diameter_mm") or 0.0) / 2.0
        return cls(int(number), kind, radius, float(entry.get("corner_radius_mm") or 0.0), float(angle) / 2.0,
                   float(entry.get("tip_diameter_mm") or 0.0) / 2.0, length, float(entry.get("pitch_mm") or 0.0),
                   entry.get("hand") or "right", family, shank, float(entry.get("stickout_mm") or 0.0),
                   float(entry.get("holder_diameter_mm") or 0.0) / 2.0, float(entry.get("holder_length_mm") or 0.0),
                   flutes > 0)

    @property
    def point(self) -> float:
        """How far the tip leads the full diameter: a cone's length, a tap's three pitches of lead."""
        if self.type == "tap":
            return 3.0 * self.pitch
        if self.type in _CONES and self.radius > 0:
            return max(0.0, self.radius - self.tip_radius) / math.tan(math.radians(self.half_angle_deg))
        return 0.0

    def height(self, d: np.ndarray) -> np.ndarray:
        """The lower surface above the tip at radial distance ``d``; inf beyond the radius."""
        d = np.abs(np.asarray(d, dtype=float))
        r = self.radius
        out = np.full(d.shape, np.inf)
        inside = d <= r + 1e-12
        di = np.minimum(d[inside], r)
        if self.type == "ball":
            out[inside] = r - np.sqrt(np.maximum(0.0, r * r - di * di))
        elif self.type == "bull":
            rc = min(self.corner_radius, r)
            dd = np.maximum(0.0, di - (r - rc))
            out[inside] = rc - np.sqrt(np.maximum(0.0, rc * rc - dd * dd))
        elif self.type in _CONES:
            out[inside] = np.maximum(0.0, di - self.tip_radius) / math.tan(math.radians(self.half_angle_deg))
        else:
            out[inside] = 0.0
        return out


def _comment_tools(comments: list[str]) -> dict[int, ToolShape]:
    """Tools from a header's ``T1: 6 mm flat`` comments, when the caller gives none (fallback)."""
    out = {}
    for text in comments:
        match = re.match(r"\s*(?:LOAD\s+)?T(\d+)(?:\s*\([^)]*\))?:\s*([\d.]+)\s*MM\s+([A-Z ]+)", text.upper())
        if match and int(match.group(1)) not in out:
            word = match.group(3).strip().split()[-1].lower()
            kind = {"flat": "flat", "ball": "ball", "drill": "drill", "nose": "bull"}.get(word, "flat")
            out[int(match.group(1))] = ToolShape.from_job({"type": kind, "diameter_mm": float(match.group(2)),
                                                           "number": int(match.group(1))})
    return out


# --- stock ---------------------------------------------------------------------------------------------------

@dataclass
class StockShape:
    """The stock in a setup's WCS: an oriented box or a cylinder (part coordinates and the part -> WCS matrix)."""

    kind: str
    to_wcs: np.ndarray                 # 4x4 part -> WCS
    lo: np.ndarray
    hi: np.ndarray
    axis: int = 2
    centre: np.ndarray | None = None
    radius: float = 0.0

    @classmethod
    def from_extras(cls, stock: dict, matrix) -> "StockShape":
        m = np.asarray(matrix, dtype=float)
        lo, hi = np.asarray(stock["min_mm"], dtype=float), np.asarray(stock["max_mm"], dtype=float)
        cyl = stock.get("cylinder")
        if cyl:
            axis = "xyz".index(cyl["axis"])
            lo, hi = lo.copy(), hi.copy()
            lo[axis], hi[axis] = min(cyl["start"], cyl["end"]), max(cyl["start"], cyl["end"])
            return cls("cylinder", m, lo, hi, axis, np.asarray(cyl["center"], dtype=float), float(cyl["radius"]))
        return cls("box", m, lo, hi)

    @classmethod
    def box(cls, lo, hi) -> "StockShape":
        return cls("box", np.eye(4), np.asarray(lo, dtype=float), np.asarray(hi, dtype=float))

    @property
    def to_part(self) -> np.ndarray:
        return np.linalg.inv(self.to_wcs)

    def corners_wcs(self) -> np.ndarray:
        corners = np.array([[x, y, z] for x in (self.lo[0], self.hi[0]) for y in (self.lo[1], self.hi[1])
                            for z in (self.lo[2], self.hi[2])])
        return corners @ self.to_wcs[:3, :3].T + self.to_wcs[:3, 3]

    def column(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """The WCS Z interval inside the stock over each (x, y); NaN where the column misses it."""
        inv = self.to_part
        base = np.stack([x, y, np.zeros_like(x)], axis=-1) @ inv[:3, :3].T + inv[:3, 3]
        d = inv[:3, 2]
        t0 = np.full(x.shape, -np.inf)
        t1 = np.full(x.shape, np.inf)
        axes = [i for i in range(3) if self.kind == "box" or i == self.axis]
        for i in axes:
            if abs(d[i]) < 1e-12:
                outside = (base[..., i] < self.lo[i]) | (base[..., i] > self.hi[i])
                t0 = np.where(outside, np.inf, t0)
            else:
                a, b = (self.lo[i] - base[..., i]) / d[i], (self.hi[i] - base[..., i]) / d[i]
                t0, t1 = np.maximum(t0, np.minimum(a, b)), np.minimum(t1, np.maximum(a, b))
        if self.kind == "cylinder":
            u, v = [i for i in range(3) if i != self.axis]
            pu, pv = base[..., u] - self.centre[u], base[..., v] - self.centre[v]
            qa = d[u] ** 2 + d[v] ** 2
            qb = 2 * (d[u] * pu + d[v] * pv)
            qc = pu * pu + pv * pv - self.radius ** 2
            if qa < 1e-12:
                t0 = np.where(qc > 0, np.inf, t0)
            else:
                disc = qb * qb - 4 * qa * qc
                root = np.sqrt(np.maximum(disc, 0.0))
                t0 = np.where(disc < 0, np.inf, np.maximum(t0, (-qb - root) / (2 * qa)))
                t1 = np.minimum(t1, (-qb + root) / (2 * qa))
        empty = t0 > t1
        return np.where(empty, np.nan, t0), np.where(empty, np.nan, t1)


# --- material models -----------------------------------------------------------------------------------------

def _stencil(radius: float, cell: float):
    half = int(math.ceil(radius / cell)) + 1
    offsets = np.arange(-half, half + 1)
    oi, oj = np.meshgrid(offsets, offsets, indexing="ij")
    return oi.ravel(), oj.ravel()


class ZMap:
    """Material over a WCS XY grid: from ``bottom`` up to ``top`` in each column (a cut lowers ``top``)."""

    def __init__(self, stock: StockShape, cell: float):
        corners = stock.corners_wcs()
        lo, hi = corners.min(axis=0), corners.max(axis=0)
        self.cell = cell
        self.x0, self.y0 = lo[0] - cell, lo[1] - cell
        self.nx = int(math.ceil((hi[0] - lo[0]) / cell)) + 3
        self.ny = int(math.ceil((hi[1] - lo[1]) / cell)) + 3
        xs = self.x0 + (np.arange(self.nx) + 0.5) * cell
        ys = self.y0 + (np.arange(self.ny) + 0.5) * cell
        gx, gy = np.meshgrid(xs, ys, indexing="ij")
        zlo, zhi = stock.column(gx, gy)
        self.top = np.where(np.isnan(zhi), -np.inf, zhi).ravel()
        self.bottom = np.where(np.isnan(zlo), np.inf, zlo).ravel()
        self.stock_top = float(np.nanmax(zhi)) if np.isfinite(self.top).any() else 0.0
        self.stock_bottom = float(np.nanmin(zlo)) if np.isfinite(self.bottom).any() else 0.0
        self._stencils: dict = {}

    def _gather(self, points: np.ndarray, tool: ToolShape, shrink: float):
        """(index, value, point row) of every cell within the tool's reach of each point: value is the height of the
        tool's lower surface over that cell."""
        cell = self.cell
        reach = max(tool.radius, 0.75 * cell)
        key = round(reach / cell, 6)
        if key not in self._stencils:
            self._stencils[key] = _stencil(reach, cell)
        oi, oj = self._stencils[key]
        ci = np.floor((points[:, 0] - self.x0) / cell).astype(int)
        cj = np.floor((points[:, 1] - self.y0) / cell).astype(int)
        ii = ci[:, None] + oi[None, :]
        jj = cj[:, None] + oj[None, :]
        cx = self.x0 + (ii + 0.5) * cell
        cy = self.y0 + (jj + 0.5) * cell
        d = np.hypot(cx - points[:, 0:1], cy - points[:, 1:2])
        if tool.radius > 0:
            prof = tool.height(d + shrink)
        else:
            prof = np.where(d <= 0.75 * cell, 0.0, np.inf)
        ok = (ii >= 0) & (ii < self.nx) & (jj >= 0) & (jj < self.ny) & np.isfinite(prof)
        rows = np.broadcast_to(np.arange(len(points))[:, None], ii.shape)
        return (ii * self.ny + jj)[ok], (points[:, 2:3] + prof)[ok], rows[ok]

    def cut(self, points: np.ndarray, tool: ToolShape) -> None:
        for start in range(0, len(points), 2048):
            idx, val, _ = self._gather(points[start:start + 2048], tool, 0.0)
            np.minimum.at(self.top, idx, val)

    def depth(self, points: np.ndarray, tool: ToolShape, shrink: float) -> np.ndarray:
        """How far the material stands over the tool's lower surface at each point (<= 0: clear)."""
        out = np.full(len(points), -np.inf)
        for start in range(0, len(points), 2048):
            idx, val, rows = self._gather(points[start:start + 2048], tool, shrink)
            solid = self.top[idx] > self.bottom[idx]
            over = np.where(solid, self.top[idx] - val, -np.inf)
            np.maximum.at(out[start:start + 2048], rows, over)
        return out


class RadialMap:
    """A bar turned on a 4th axis (A about WCS X): its radius over (x, angle) about the axis line (y0, z0)."""

    def __init__(self, x0: float, x1: float, centre: tuple, radius: float, cell: float):
        self.cell = cell
        self.x0 = x0 - cell
        self.nx = int(math.ceil((x1 - x0) / cell)) + 3
        self.nt = max(64, int(math.ceil(2 * math.pi * radius / cell)))
        self.yc, self.zc = centre
        self.radius = radius
        self.r = np.full((self.nx, self.nt), radius)
        inside = (self.x0 + (np.arange(self.nx) + 0.5) * cell >= x0) & (self.x0 + (np.arange(self.nx) + 0.5) * cell
                                                                         <= x1)
        self.r[~inside] = 0.0
        self.r = self.r.ravel()

    def _gather(self, points: np.ndarray, tool: ToolShape, shrink: float):
        rho = np.hypot(points[:, 1] - self.yc, points[:, 2] - self.zc)
        theta = np.arctan2(points[:, 1] - self.yc, points[:, 2] - self.zc)
        reach = max(tool.radius, 0.75 * self.cell)
        half_x = int(math.ceil(reach / self.cell)) + 1
        dt = 2 * math.pi / self.nt
        half_t = int(math.ceil(reach / max(self.radius * 0.25, 1e-6) / dt)) + 1
        half_t = min(half_t, self.nt // 2)
        oi, oj = np.meshgrid(np.arange(-half_x, half_x + 1), np.arange(-half_t, half_t + 1), indexing="ij")
        oi, oj = oi.ravel(), oj.ravel()
        ci = np.floor((points[:, 0] - self.x0) / self.cell).astype(int)
        cj = np.floor((theta % (2 * math.pi)) / dt).astype(int)
        ii = ci[:, None] + oi[None, :]
        jj = (cj[:, None] + oj[None, :]) % self.nt
        cx = self.x0 + (ii + 0.5) * self.cell
        ct = (jj + 0.5) * dt
        dtheta = (ct - theta[:, None] + math.pi) % (2 * math.pi) - math.pi
        lateral = np.hypot(cx - points[:, 0:1], rho[:, None] * np.sin(np.abs(dtheta)))
        prof = tool.height(lateral + shrink) if tool.radius > 0 else np.where(lateral <= 0.75 * self.cell, 0, np.inf)
        cosine = np.cos(dtheta)
        ok = (ii >= 0) & (ii < self.nx) & np.isfinite(prof) & (cosine > 0.2)
        val = rho[:, None] / np.where(cosine > 0.2, cosine, 1.0) + prof
        rows = np.broadcast_to(np.arange(len(points))[:, None], ii.shape)
        return (ii * self.nt + jj)[ok], val[ok], rows[ok]

    def cut(self, points: np.ndarray, tool: ToolShape) -> None:
        for start in range(0, len(points), 1024):
            idx, val, _ = self._gather(points[start:start + 1024], tool, 0.0)
            np.minimum.at(self.r, idx, val)

    def depth(self, points: np.ndarray, tool: ToolShape, shrink: float) -> np.ndarray:
        out = np.full(len(points), -np.inf)
        for start in range(0, len(points), 1024):
            idx, val, rows = self._gather(points[start:start + 1024], tool, shrink)
            np.maximum.at(out[start:start + 1024], rows, self.r[idx] - val)
        return out


class LatheMap:
    """A bar on a lathe: material between ``inner`` (the bore) and ``outer`` radius over WCS Z bins."""

    def __init__(self, radius: float, z0: float, z1: float, cell: float, sliver: float):
        self.cell = cell
        self.z0 = z0 - cell
        self.n = int(math.ceil((z1 - z0) / cell)) + 3
        zs = self.z0 + (np.arange(self.n) + 0.5) * cell
        inside = (zs >= z0) & (zs <= z1)
        self.outer = np.where(inside, radius, 0.0)
        self.inner = np.zeros(self.n)
        self.radius = radius
        self.z1 = z1
        self.sliver = int(round(sliver / cell))

    def _bins(self, z: np.ndarray) -> np.ndarray:
        return np.clip(np.floor((z - self.z0) / self.cell).astype(int), 0, self.n - 1)

    def cut(self, r: np.ndarray, z: np.ndarray, tool: ToolShape) -> None:
        bins = self._bins(z)
        inside = (z >= self.z0) & (z <= self.z0 + self.n * self.cell)
        for k, b, rr in zip(range(len(bins)), bins, r):
            if not inside[k]:
                continue
            if tool.family != "lathe":                 # a drill or a mill tool on the axis: the bore
                self.inner[b] = max(self.inner[b], rr + tool.radius)
            elif rr - self.inner[b] < self.outer[b] - rr:
                self.inner[b] = max(self.inner[b], rr)
            else:
                self.outer[b] = min(self.outer[b], rr)

    def solid(self) -> tuple[np.ndarray, np.ndarray]:
        """(inner, outer) opened by ``sliver`` along Z (a min filter on the outer radius, a max filter on the bore):
        a sliver thinner than 2 * sliver between two passes counts as cut (an insert's edge takes it)."""
        inner, outer = self.inner.copy(), self.outer.copy()
        for shift in range(1, self.sliver + 1):
            outer[shift:] = np.minimum(outer[shift:], self.outer[:-shift])
            outer[:-shift] = np.minimum(outer[:-shift], self.outer[shift:])
            inner[shift:] = np.maximum(inner[shift:], self.inner[:-shift])
            inner[:-shift] = np.maximum(inner[:-shift], self.inner[shift:])
        return inner, outer

    def depth(self, r: np.ndarray, z: np.ndarray, tool: ToolShape) -> np.ndarray:
        inner, outer = self.solid()
        bins = self._bins(z)
        reach = tool.radius if tool.family != "lathe" else 0.0
        # How far the tool would have to move out radially, either way, to leave the material.
        into = np.minimum(outer[bins] - (r - reach), (r + reach) - inner[bins])
        out = np.where(outer[bins] > inner[bins], into, -np.inf)
        beyond = (z < self.z0) | (z > self.z0 + self.n * self.cell)
        return np.where(beyond, -np.inf, out)


# --- sampling ------------------------------------------------------------------------------------------------

def _segment(start, end, step: float) -> np.ndarray:
    start, end = np.asarray(start, dtype=float), np.asarray(end, dtype=float)
    length = float(np.linalg.norm(end - start))
    n = max(1, int(math.ceil(length / step)))
    t = np.linspace(0.0, 1.0, n + 1)[:, None]
    return start + (end - start) * t


def _arc(move, start, end, step: float) -> np.ndarray:
    u, v, w = {"G17": (0, 1, 2), "G18": (2, 0, 1), "G19": (1, 2, 0)}[move.plane]
    c = move.centre
    a0 = math.atan2(start[v] - c[v], start[u] - c[u])
    a1 = math.atan2(end[v] - c[v], end[u] - c[u])
    radius = math.hypot(start[u] - c[u], start[v] - c[v])
    sweep = a1 - a0
    if move.kind == "arc_cw":
        while sweep >= -1e-9:
            sweep -= 2 * math.pi
    else:
        while sweep <= 1e-9:
            sweep += 2 * math.pi
    n = max(2, int(math.ceil(max(radius * abs(sweep), abs(end[w] - start[w])) / step)))
    t = np.linspace(0.0, 1.0, n + 1)
    out = np.zeros((n + 1, 3))
    out[:, u] = c[u] + radius * np.cos(a0 + sweep * t)
    out[:, v] = c[v] + radius * np.sin(a0 + sweep * t)
    out[:, w] = start[w] + (end[w] - start[w]) * t
    return out


def _tool_axis(abc: dict, setup_rotary: dict) -> np.ndarray:
    """The tool axis in the setup's WCS for rotary positions (degrees): ``R(abc_s) R(abc)^T z`` with
    ``R = Rx(a) Ry(b) Rz(c)`` (the documented table convention; one formula for A+C, B+C and A alone)."""
    def rot(values):
        a, b, c = (math.radians(values.get(k, 0.0) or 0.0) for k in "abc")
        rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
        ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
        rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
        return rx @ ry @ rz

    return rot(setup_rotary) @ rot(abc).T @ np.array([0.0, 0.0, 1.0])


# --- the simulation ------------------------------------------------------------------------------------------

@dataclass
class _State:
    pos: list = field(default_factory=lambda: [None, None, None])
    abc: dict = field(default_factory=dict)
    spindle: str = "off"
    spindle_line: int = 0
    spun_up: bool = True
    rpm: float = 0.0
    tool: int | None = None
    pending_tool: int | None = None
    entry: str = "start"
    xy_since_high: bool = False
    tcp: bool = False
    last_cut: bool = False
    beam: bool = False
    beam_z: float | None = None
    pierced: bool = True
    inline_s: float = 0.0
    m29: bool = False
    tap_in: bool = False
    threaded: bool = True
    loads: int = 0
    units: str | None = None
    absolute: bool | None = None
    wcs: bool = False
    moved: bool = False
    length: bool = False


class _Sim:
    def __init__(self, *, kind: str, post: str, stock: StockShape | None = None, tools: dict | None = None,
                 clearance: float | None = None, retract: float | None = None, travel=None, rotary_limits=None,
                 kinematics: str = "ac_trunnion", setup_rotary: dict | None = None, fixtures=(),
                 diameter: bool = True, options: dict | None = None, cell_mm: float = 0.5, tol_mm: float = 0.05,
                 below_bottom_mm: float = 1.0, lathe_sliver_mm: float = 0.5, wire_kerf_mm: float = 0.3):
        self.kind, self.post = kind, post
        self.stock = stock
        self.tools = dict(tools or {})
        self.clearance, self.retract = clearance, retract
        self.travel = travel
        self.rotary_limits = rotary_limits or {}
        self.kinematics = kinematics
        self.setup_rotary = {k.lower()[0]: float(v) for k, v in (setup_rotary or {}).items()}
        self.fixtures = [(np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)) for lo, hi in fixtures]
        self.diameter = diameter
        self.options = dict(options or {})
        self.cell, self.tol = cell_mm, tol_mm
        self.below_bottom = below_bottom_mm
        self.sliver = lathe_sliver_mm
        self.wire_kerf = wire_kerf_mm
        self.findings: list[Finding] = []
        self._seen: set = set()
        self.lathe = kind == "lathe"
        self.span = {a: [math.inf, -math.inf] for a in "XYZABC"}
        self.material = None
        self.mode = None
        self.wire_mask = None

    # -- findings --
    def flag(self, rule: str, file: int, line: int, message: str) -> None:
        key = (rule, file, line)
        if key not in self._seen:
            self._seen.add(key)
            self.findings.append(Finding(rule, file, line, message))

    # -- material --
    def _material(self, program) -> None:
        if self.material is not None or self.stock is None:
            return
        if self.lathe:
            corners = self.stock.corners_wcs()
            radius = self.stock.radius if self.stock.kind == "cylinder" else float(
                max(np.abs(corners[:, 0]).max(), np.abs(corners[:, 1]).max()))
            self.material = LatheMap(radius, float(corners[:, 2].min()), float(corners[:, 2].max()),
                                     min(self.cell, 0.1), self.sliver)
            self.mode = "lathe"
            return
        if self.kind in ("wire_edm",):
            self.mode = "wire"
            corners = self.stock.corners_wcs()
            self.wire_lo, self.wire_hi = corners.min(axis=0), corners.max(axis=0)
            nx = int(math.ceil((self.wire_hi[0] - self.wire_lo[0]) / 0.1)) + 1
            ny = int(math.ceil((self.wire_hi[1] - self.wire_lo[1]) / 0.1)) + 1
            self.wire_mask = np.zeros((nx, ny), bool)
            return
        if self.kind not in MILL_KINDS:
            return
        moving_a = {m.abc.get("A") for m in program.moves if "A" in m.given} if program is not None else set()
        tcp = any(e.kind == "length" and e.data.get("code") in ("G43.4", "G234") for e in program.timeline
                  if isinstance(e, gcode_reader.Event))
        if self.kind == "mill4" and tcp and len(moving_a) > 1 and self.stock.kind == "cylinder":
            axis_wcs = self.stock.to_wcs[:3, :3] @ np.eye(3)[self.stock.axis]
            if abs(abs(axis_wcs[0]) - 1.0) < 1e-6:
                centre = self.stock.to_wcs[:3, :3] @ self.stock.centre + self.stock.to_wcs[:3, 3]
                corners = self.stock.corners_wcs()
                self.material = RadialMap(float(corners[:, 0].min()), float(corners[:, 0].max()),
                                          (float(centre[1]), float(centre[2])), self.stock.radius, self.cell)
                self.mode = "radial"
                return
        self.material = ZMap(self.stock, self.cell)
        self.mode = "zmap"

    def tool_shape(self) -> ToolShape:
        number = self._tool
        if number is not None and number in self.tools:
            return self.tools[number]
        return ToolShape(number or 0)

    # -- the walk --
    def run(self, file: int, text: str) -> None:
        program = gcode_reader.read(text, lathe=self.lathe, diameter=self.diameter)
        if not self.tools:
            self.tools = _comment_tools(program.comments)
        self._material(program)
        st = _State()
        st.threaded = self.kind == "wire_edm"
        if self.lathe:
            st.pos[1] = 0.0
        self._zwords = any("Z" in m.given for m in program.moves if m.kind != "dwell")
        self._tool = None
        self._pending_cut: list = []
        if self.post == "grbl" and self.kind != "laser":
            loads = sum(1 for c in program.comments if c.strip().upper().startswith("LOAD T"))
            if loads > 1:
                self.flag("tool_change", file, 0, f"{loads} tools loaded in one GRBL file: GRBL has no tool table, "
                                                  "so the next tool's length is unknown")
            for c in program.comments:
                m = re.match(r"\s*LOAD\s+T(\d+)", c.upper())
                if m:
                    self._tool = int(m.group(1))
                    break
        for item in program.timeline:
            if isinstance(item, gcode_reader.Event):
                self._event(file, item, st)
            else:
                self._move(file, item, st)
        self._flush()

    # -- events --
    def _home_z(self, st) -> None:
        self._flush()
        st.pos[2] = TOP
        if st.entry in ("start", "done"):
            st.entry = "high"
            st.xy_since_high = False

    def _event(self, file: int, ev, st) -> None:
        kind, data, line = ev.kind, ev.data, ev.line
        if kind == "home":
            axes = data.get("axes", {})
            code = data.get("code")
            rotary = {a: v for a, v in axes.items() if a in "ABC"}
            if self.lathe:
                if code in ("G28", "G30"):
                    self._lathe_home_path(file, line, st)
                    st.pos = [TOP, 0.0, TOP]
                    st.entry = "high"
                return
            if rotary:
                self._rotary_turn(file, line, st, rapid=True)
            if code == "G30" and not axes:
                st.pos = [None, None, TOP]
                self._home_z(st)
            if "Z" in axes and (code in ("G28", "G30") or abs(axes["Z"]) < 1e-9):
                self._home_z(st)
            elif "Z" in axes:
                st.pos[2] = None
            if "X" in axes or "Y" in axes:
                st.pos[0] = st.pos[1] = None
            for a in rotary:
                st.abc[a] = 0.0
        elif kind == "tool":
            st.pending_tool = data["t"]
            if self.lathe:
                number = data["t"] // 100 if data["t"] >= 100 else data["t"]
                self._tool_change(file, line, st, number)
        elif kind == "m6":
            if not self.lathe:
                self._tool_change(file, line, st, st.pending_tool)
        elif kind == "spindle":
            m = data.get("m")
            if data.get("s") is not None and m in (3, 4):
                st.rpm = float(data["s"])
            if self.kind in SPINDLE_KINDS:
                was = st.spindle
                st.spindle = {3: "cw", 4: "ccw", 5: "off"}[m]
                if m in (3, 4) and was == "off":
                    st.spun_up = False
                if m == 5:
                    st.spun_up = True
                if m in (3, 4) and was != st.spindle:
                    st.m29 = False
            else:
                self._beam(file, line, st, m, data.get("s"))
        elif kind == "speed":
            if data.get("s") is not None and not any(g in ("G50", "G96") for g in data.get("gs", ())):
                st.rpm = float(data["s"])
            if self.kind == "laser" and self.post == "marlin":
                st.inline_s = float(data["s"])
        elif kind == "stop":
            if self.kind in SPINDLE_KINDS:
                st.spindle = "off"
                st.spun_up = True
        elif kind == "length":
            code = data.get("code")
            if code in ("G43.4", "G234"):
                st.tcp = True
            elif code == "G49":
                st.tcp = False
            st.length = code != "G49"
            h = data.get("h")
            if code != "G49" and h is not None and self._tool is not None and int(h) != self._tool:
                self.flag("length", file, line, f"{code} H{int(h)} with T{self._tool} in the spindle: the wrong "
                                                "tool length")
        elif kind == "mode":
            code = data.get("code")
            if code in ("G20", "G21"):
                st.units = code
                if code == "G20":
                    self.flag("modal", file, line, "G20: the program's numbers are millimetres")
            else:
                st.absolute = code == "G90"
        elif kind == "wcs":
            st.wcs = True
        elif kind == "tilt":
            if data.get("code") in ("G53.1",) and st.pos[2] != TOP and (st.pos[2] is None or self.clearance is None
                                                                            or st.pos[2] < self.clearance - 1e-6):
                self.flag("rotary", file, line, "G53.1 turns the table to the tilted plane with the tool not at the "
                                                "machine's top")
        elif kind == "mcode":
            m = data.get("m")
            if m == 29:
                st.m29 = True
            if self.kind == "wire_edm":
                cut = self.options.get("wire_cut", "M50")
                thread = self.options.get("wire_thread", "M60")
                if f"M{m:g}" == cut:
                    st.threaded = False
                elif f"M{m:g}" == thread:
                    st.threaded = True
                    if st.pos[0] is not None:
                        self._wire_mark(np.array([[st.pos[0], st.pos[1], 0.0]]), 1.0)
        elif kind == "rough" and self.mode == "lathe":
            self._rough(data["rough"])
        elif kind == "g92":
            axes = data.get("axes", {})
            for i, a in enumerate("XY"):
                if a in axes:
                    st.pos[i] = float(axes[a])
            if st.pos[2] is None:
                st.pos[2] = 0.0
            if self.kind == "wire_edm" and st.pos[0] is not None:
                self._wire_mark(np.array([[st.pos[0], st.pos[1], 0.0]]), 1.0)

    def _rough(self, rough: dict) -> None:
        """A native lathe roughing cycle (G71): it leaves its finish profile plus the allowance."""
        points = rough.get("profile") or []
        if len(points) < 2:
            return
        u = float(rough.get("u", 0.0)) / (2.0 if self.diameter else 1.0)
        m = self.material
        zs = m.z0 + (np.arange(m.n) + 0.5) * m.cell
        for (r0, z0), (r1, z1) in zip(points[:-1], points[1:]):
            lo, hi = min(z0, z1), max(z0, z1)
            inside = (zs >= lo) & (zs <= hi)
            if not inside.any():
                continue
            if abs(z1 - z0) < 1e-12:                    # a shoulder: the larger radius stands there
                r = max(r0, r1) if u >= 0 else min(r0, r1)
            else:
                r = r0 + (r1 - r0) * (zs[inside] - z0) / (z1 - z0)
            if u >= 0:
                m.outer[inside] = np.minimum(m.outer[inside], r + u)
            else:
                m.inner[inside] = np.maximum(m.inner[inside], r + u)

    def _tool_change(self, file: int, line: int, st, number) -> None:
        self._flush()
        if self.lathe:
            if not (st.pos[0] == TOP and st.pos[2] == TOP):
                self.flag("tool_change", file, line, "the turret indexes away from its home (no G28 U0 W0 / G30 "
                                                    "since the last move): the tools swing through the part")
            st.pos = [TOP, 0.0, TOP]
            st.entry = "high"
        else:
            # Mach3 machines are often never homed, so its post changes tools at the program's clearance in the work
            # offset, never G53 (machine Z0 may stand below the work): that is a safe height there.
            clear_here = (self.post == "mach3" and self.clearance is not None and st.pos[2] not in (TOP, None)
                          and st.pos[2] >= self.clearance - 1e-6)
            if self.post != "haas" and st.pos[2] != TOP and st.pos[2] is not None and not clear_here:
                self.flag("tool_change", file, line, f"M6 with Z at {st.pos[2]:g} (no G53 Z0 / G28 Z0 since): the tool "
                                                    "change happens over the work")
            if self.post != "haas" and st.pos[2] is None and st.entry != "start":
                self.flag("tool_change", file, line, "M6 with Z at an unknown height")
            if self.post == "haas":
                st.pos[2] = TOP                    # the Haas tool change takes Z home itself
            st.spindle = "off"
            st.spun_up = True
            st.entry = "high" if st.pos[2] == TOP else "start"
            st.xy_since_high = False
            st.tcp = False
            st.length = False
        self._tool = number
        st.m29 = False
        st.last_cut = False
        st.tap_in = False

    def _beam(self, file: int, line: int, st, m, s) -> None:
        on = m in (3, 4) and (s is None or float(s) > 0)
        if self.kind == "laser" and self.post == "grbl":
            st.beam_mode = m
        if on and not st.beam:
            st.beam = True
            st.beam_z = st.pos[2]
            st.pierced = False
            st.beam_on_line = line
        elif m == 5:
            st.beam = False
            st.pierced = True

    # -- moves --
    def _flush(self) -> None:
        """Cut what the feed moves since the last rapid swept (the material only matters at the next rapid), after
        checking that a tap goes only where a drill went and that the shank and holder stay out of the material."""
        if not self._pending_cut:
            return
        points = np.vstack([chunk for chunk, _, _ in self._pending_cut])
        lines = np.concatenate([np.full(len(chunk), line) for chunk, _, line in self._pending_cut])
        file = self._pending_cut[0][1]
        self._pending_cut = []
        tool = self.tool_shape()
        if self.mode == "zmap":
            if tool.type == "tap":
                depth = self.material.depth(points[:, :3], tool, 0.05)
                worst = int(np.argmax(depth))
                if depth[worst] > self.tol:
                    self.flag("tap", file, int(lines[worst]), f"the tap cuts {depth[worst]:.2f} mm into material no "
                                                              "drill removed")
            self.material.cut(points[:, :3], tool)
            tilted = points[np.abs(points[:, 5]) < 0.9999]
            for s in np.arange(self.cell * 0.5, tool.length + 1e-9, self.cell * 0.5):
                if not len(tilted):
                    break
                body = tilted[:, :3] + s * tilted[:, 3:6]
                self.material.cut(body, ToolShape(tool.number, "flat", tool.radius))
            self._holder_rule(file, lines, points[:, :3], points[:, 3:6], tool)
        elif self.mode == "radial":
            self.material.cut(points[:, :3], tool)
        elif self.mode == "lathe":
            self.material.cut(points[:, 0], points[:, 2], tool)

    def _holder_rule(self, file, lines, points, axes, tool) -> None:
        """The shank (from the flutes' top to the stickout) and the holder (above it) against the material."""
        pieces = []
        if tool.flutes_known and tool.stickout > tool.length and tool.shank_radius > 0:
            pieces.append((tool.length, tool.stickout, tool.shank_radius, "shank"))
        if tool.stickout > 0 and tool.holder_radius > 0:
            pieces.append((tool.stickout, tool.stickout + max(tool.holder_length, 1.0), tool.holder_radius, "holder"))
        if not pieces or self.mode != "zmap":
            return
        vertical = np.abs(axes[:, 2]) >= 0.9999
        for low, high, radius, word in pieces:
            disc = ToolShape(tool.number, "flat", radius)
            depth = self.material.depth(points + low * axes, disc, 0.05)
            if not vertical.all():
                for s in np.arange(low + self.cell, high + 1e-9, self.cell):
                    depth = np.where(vertical, depth, np.maximum(depth, self.material.depth(points + s * axes, disc,
                                                                                            0.05)))
            worst = int(np.argmax(depth))
            if depth[worst] > self.tol:
                p = points[worst]
                self.flag("holder", file, int(lines[worst]), f"the tool's {word} runs {depth[worst]:.2f} mm into the "
                                                             f"material with the tip at ({p[0]:.2f}, {p[1]:.2f}, "
                                                             f"{p[2]:.2f})")
                return

    def _resolve(self, move, st) -> list:
        end = []
        for i, axis in enumerate("XYZ"):
            if axis in move.given:
                end.append(float(move.end[i]))
            else:
                end.append(st.pos[i])
        if self.lathe:
            end[1] = 0.0
        return end

    def _concrete(self, p: list, st) -> np.ndarray | None:
        """A position with TOP clipped to a height above everything (for sampling a move from the top)."""
        if any(v is None for v in p):
            return None
        out = []
        for i, v in enumerate(p):
            if v == TOP:
                if self.lathe:
                    ref = self.material.radius if i == 0 and self.material is not None else (
                        self.material.z1 if self.material is not None else 0.0)
                else:
                    ref = (self.material.stock_top if self.mode == "zmap" else
                           (self.material.radius + self.material.zc) if self.mode == "radial" else 0.0)
                    ref = max(ref, self.clearance or ref)
                v = ref + 50.0
            out.append(float(v))
        return np.array(out)

    def _axes_along(self, st, abc_end: dict, n: int) -> np.ndarray | None:
        if self.kind not in ("mill4", "mill5") or not st.tcp:
            return None
        names = [a for a in "abc" if a.upper() in "ABC"]
        start = {a: (st.abc.get(a.upper()) or 0.0) for a in names}
        end = {a: abc_end.get(a, start[a]) for a in names}
        out = []
        for t in np.linspace(0.0, 1.0, n):
            out.append(_tool_axis({a: start[a] + (end[a] - start[a]) * t for a in names}, self.setup_rotary))
        return np.array(out)

    def _rotary_turn(self, file: int, line: int, st, *, rapid: bool) -> None:
        """Rule 5 for a move (or a home) that turns a rotary axis."""
        z = st.pos[2]
        if st.tcp:
            if rapid and st.last_cut and z is not None and z != TOP:
                safe = self.retract if self.retract is not None else self.clearance
                if safe is not None and z < safe - 1e-6:
                    self.flag("rotary", file, line, f"the table turns straight out of a cut with the tip at Z{z:g}, "
                                                    f"below the retract height Z{safe:g}")
            return                                 # a turn while cutting is what TCP is for
        if not rapid:
            self.flag("rotary", file, line, "a rotary axis turns while cutting without tool centre point control")
            return
        if z == TOP:
            return
        if z is None or self.clearance is None or z < self.clearance - 1e-6:
            where = "an unknown height" if z is None else f"Z{z:g}"
            self.flag("rotary", file, line, f"a rotary axis turns with the tool at {where}, below the clearance "
                                            "height")

    def _move(self, file: int, move, st) -> None:
        if move.kind == "dwell":
            if self.kind in SPINDLE_KINDS and st.spindle != "off":
                st.spun_up = True
            if st.beam:
                if self.post == "grbl" and self.kind == "laser" and getattr(st, "beam_mode", 3) == 4:
                    self.flag("beam", file, move.line, "a pierce dwell in M4 (dynamic power) fires nothing while "
                                                         "the head stands still")
                else:
                    st.pierced = True
            return
        start = list(st.pos)
        end = self._resolve(move, st)
        rotary = {a.lower(): float(move.abc[a]) for a in "ABC" if a in move.given}
        turning = {a: v for a, v in rotary.items() if st.abc.get(a.upper()) is None
                   or abs(st.abc[a.upper()] - v) > 1e-9}
        cutting = move.kind != "rapid"
        line = move.line
        xy_moves = (("X" in move.given and start[0] != end[0]) or ("Y" in move.given and start[1] != end[1]))
        z_given = "Z" in move.given
        self._modal_rule(file, line, move, st, z_given)
        # rule 4: the entry
        if self.kind in SPINDLE_KINDS and not self.lathe and move.cycle is None:
            self._entry(file, line, st, start, end, xy_moves, z_given, bool(turning), cutting)
        elif self.lathe and st.entry == "high" and move.kind == "rapid":
            st.entry = "done"
        elif self.kind in BEAM_KINDS and st.entry == "start" and any(v is None for v in start):
            if "Z" in move.given and not xy_moves:
                st.entry = "done"
            elif xy_moves and self._zwords:
                self.flag("entry", file, line, "the first move crosses X Y with the head at an unknown height; "
                                               "take Z to a safe height first")
                st.entry = "done"
        # rule 2: spindle
        if cutting and self.kind in SPINDLE_KINDS:
            if st.spindle == "off":
                self.flag("spindle_off", file, line, "a cutting move with the spindle stopped")
            elif not st.spun_up and self.post == "grbl":
                self.flag("spinup", file, line, "a cutting move right after the spindle starts, with no dwell for it "
                                                "to reach speed (GRBL does not wait)")
                st.spun_up = True
        # rule 5: rotary
        if turning and self.kind in ("mill4", "mill5"):
            self._rotary_turn(file, line, st, rapid=not cutting)
        # rule 7: arcs
        if move.kind in ("arc_cw", "arc_ccw") and all(v is not None and v != TOP for v in start):
            self._arc_rule(file, line, move, start, end)
        # rule 6: taps
        self._tap_rule(file, line, move, st, start, end)
        # rule 9: the beam
        if self.kind in BEAM_KINDS:
            self._beam_rule(file, line, move, st, start, end, xy_moves)
        # rule 10 and the material
        a = self._concrete(start, st)
        b = self._concrete(end, st)
        if a is not None and b is not None:
            if move.kind in ("arc_cw", "arc_ccw"):
                points = _arc(move, a, b, self.cell * 0.5)
            else:
                points = _segment(a, b, self.cell * 0.5)
            if turning and st.tcp and len(points) < 2:
                points = np.vstack([points, points[-1:]])
            if turning and st.tcp:
                # A turn under TCP swings the tool round its tip: sample the swing every degree.
                swing = max(abs(v - (st.abc.get(k.upper()) or 0.0)) for k, v in turning.items())
                n = max(len(points), int(math.ceil(swing)) + 1)
                if n > len(points):
                    t = np.linspace(0.0, 1.0, n)[:, None]
                    points = points[0] + (points[-1] - points[0]) * t if move.kind not in ("arc_cw", "arc_ccw") \
                        else points[np.minimum((t[:, 0] * (len(points) - 1)).round().astype(int), len(points) - 1)]
            axes = self._axes_along(st, rotary, len(points))
            if TOP not in start and TOP not in end:
                self._travel(points, rotary)
            if self.kind == "wire_edm":
                if cutting:
                    self._wire_mark(points, self.wire_kerf)
                elif st.threaded and xy_moves:
                    self._wire_rule(file, line, points)
            elif self.material is not None:
                if cutting:
                    if axes is None:
                        axes = np.tile([0.0, 0.0, 1.0], (len(points), 1))
                    self._pending_cut.append((np.hstack([points, axes]), file, line))
                else:
                    self._flush()
                    self._rapid_rule(file, line, points, axes)
            self._table_and_fixtures(file, line, points)
        for i in range(3):
            st.pos[i] = end[i]
        for letter, v in rotary.items():
            st.abc[letter.upper()] = v
        st.last_cut = cutting

    def _modal_rule(self, file, line, move, st, z_given) -> None:
        """Millimetres, absolute and a work offset before the first move; a mill's Z only under its tool length."""
        if not st.moved:
            st.moved = True
            if st.units != "G21":
                self.flag("modal", file, line, "the first move comes before G21 (millimetres)")
            iso_lathe = self.lathe and self.post in ("fanuc", "haas")      # system A: G90 is a turning cycle there
            if st.absolute is not True and not iso_lathe:
                self.flag("modal", file, line, "the first move comes before G90 (absolute)")
            if not st.wcs and self.post not in ("marlin", "wire_edm"):
                self.flag("modal", file, line, "the first move comes before a work offset (G54..G59)")
        if st.absolute is False:
            self.flag("modal", file, line, "a move in incremental mode (G91 left on after a home)")
        iso_mill = self.post in ("linuxcnc", "fanuc", "haas", "mach3") and self.kind in MILL_KINDS
        if iso_mill and z_given and self._tool is not None and not st.length:
            self.flag("length", file, line, f"Z moves with no tool length offset for T{self._tool} (no G43 H since "
                                            "the tool change)")

    def _entry(self, file, line, st, start, end, xy_moves, z_given, turning, cutting) -> None:
        if st.entry == "done":
            return
        safe = self.clearance if self.clearance is not None else (
            self.material.stock_top + 1.0 if self.mode == "zmap" else None)
        if st.entry == "start":
            if cutting or xy_moves or turning or not z_given:
                self.flag("entry", file, line, "the first motion moves X Y (or turns or cuts) before Z is at a safe "
                                               "height")
                st.entry = "done"
                return
            if end[2] is not None and safe is not None and end[2] < safe - 1e-6:
                self.flag("entry", file, line, f"the first motion takes Z to {end[2]:g}, below the safe height "
                                               f"{safe:g}, with X Y unknown")
            st.entry = "high"
            st.xy_since_high = False
            return
        # high: Z is safe, X Y may be unknown
        if turning and st.xy_since_high and self.kind == "mill5":
            self.flag("entry", file, line, "the rotary axes turn after X Y were positioned: turn them first, with "
                                           "the tool at the top")
        down = z_given and end[2] is not None and (start[2] == TOP or start[2] is None or end[2] < start[2] - 1e-9)
        if down:
            if not st.xy_since_high and (start[0] is None or start[1] is None):
                self.flag("entry", file, line, "Z comes down before X Y are positioned")
            elif xy_moves:
                self.flag("entry", file, line, "Z comes down from the top in the same move as X Y (a diagonal "
                                               "plunge); position X Y first")
            st.entry = "done"
            return
        if xy_moves:
            st.xy_since_high = True
        if cutting:
            st.entry = "done"

    def _lathe_home_path(self, file, line, st) -> None:
        """A lathe home (G28 U0 W0, G30) runs straight from here to +X +Z: nothing may stand in that quadrant."""
        if self.material is None or st.pos[0] is None or st.pos[0] == TOP or st.pos[2] is None or st.pos[2] == TOP:
            return
        inner, outer = self.material.solid()
        zs = self.material.z0 + (np.arange(self.material.n) + 0.5) * self.material.cell
        r, z = st.pos[0], st.pos[2]
        hit = (zs >= z + self.tol) & (outer > inner) & (outer > r + self.tol) & (inner < outer)
        hit &= outer - np.maximum(inner, r) > self.tol
        if hit.any():
            self.flag("rapid_into_stock", file, line, f"the home move from X{2 * r if self.diameter else r:g} "
                                                      f"Z{z:g} runs through the bar")

    def _rapid_rule(self, file, line, points, axes) -> None:
        tool = self.tool_shape()
        if self.mode == "lathe":
            depth = self.material.depth(points[:, 0], points[:, 2], tool)
        elif self.mode == "zmap" and axes is not None and np.any(np.abs(axes[:, 2]) < 0.9999):
            depth = self.material.depth(points, tool, 0.02)
            for s in np.arange(self.cell * 0.5, tool.length + 1e-9, self.cell * 0.5):
                body = points + s * axes
                depth = np.maximum(depth, self.material.depth(body, ToolShape(tool.number, "flat", tool.radius),
                                                              0.0))
        elif self.mode == "radial" and axes is not None:
            # The bar turns under the tool: the body up the tool's axis (to its stickout) may swing into it.
            depth = self.material.depth(points, tool, 0.02)
            reach = max(tool.length, tool.stickout)
            for s in np.arange(self.cell, reach + 1e-9, self.cell):
                radius = tool.radius if s <= tool.length or tool.shank_radius <= 0 else tool.shank_radius
                body = points + s * axes
                depth = np.maximum(depth, self.material.depth(body, ToolShape(tool.number, "flat", radius), 0.0))
        else:
            depth = self.material.depth(points, tool, 0.02)
        worst = int(np.argmax(depth))
        if depth[worst] > self.tol:
            p = points[worst]
            self.flag("rapid_into_stock", file, line, f"a rapid runs {depth[worst]:.2f} mm into uncut material at "
                                                      f"({p[0]:.2f}, {p[1]:.2f}, {p[2]:.2f})")
        if self.mode == "zmap":
            vertical = np.tile([0.0, 0.0, 1.0], (len(points), 1))
            self._holder_rule(file, np.full(len(points), line), points, axes if axes is not None else vertical, tool)

    def _table_and_fixtures(self, file, line, points) -> None:
        if self.mode == "zmap" and self.kind in ("mill", "router") and not self.setup_rotary:
            low = points[:, 2].min()
            tool = self.tool_shape()
            if low < self.material.stock_bottom - self.below_bottom - tool.point - 0.01:      # 0.01: posted digits
                self.flag("table", file, line, f"the tip goes to Z{low:.2f}, "
                                               f"{self.material.stock_bottom - low:.2f} mm under the stock's bottom")
        if self.fixtures and self.stock is not None and self.mode == "zmap":
            tool = self.tool_shape()
            inv = self.stock.to_part
            reach = max(tool.radius, 0.0)
            for s in np.arange(0.0, max(tool.length, 1.0) + 30.0, 1.0):
                body = points + np.array([0.0, 0.0, s])
                part = body @ inv[:3, :3].T + inv[:3, 3]
                for lo, hi in self.fixtures:
                    gap = np.linalg.norm(np.maximum(0.0, np.maximum(lo - part, part - hi)), axis=1)
                    if np.any(gap < reach - 1e-6) or np.any(gap == 0.0):
                        self.flag("fixture", file, line, "the tool runs into a fixture keep-out")
                        return

    def _travel(self, points, rotary) -> None:
        for i, a in enumerate("XYZ"):
            column = points[:, i]
            self.span[a][0] = min(self.span[a][0], float(column.min()))
            self.span[a][1] = max(self.span[a][1], float(column.max()))
        for a, v in rotary.items():
            self.span[a.upper()][0] = min(self.span[a.upper()][0], v)
            self.span[a.upper()][1] = max(self.span[a.upper()][1], v)

    def finish(self) -> None:
        if self.travel:
            axes = "XZ" if self.lathe else "XYZ"
            for value, axis in zip(self.travel, axes):
                lo, hi = self.span[axis]
                if not math.isfinite(lo):
                    continue
                spread = (hi - lo) * (2.0 if self.lathe and axis == "X" and self.diameter else 1.0)
                if spread > float(value) + 1e-6:
                    self.flag("travel", -1, 0, f"the program spans {spread:.1f} mm in {axis}, beyond the machine's "
                                               f"{float(value):g} mm travel")
        for axis, (lo, hi) in self.rotary_limits.items():
            span = self.span[axis.upper()]
            if math.isfinite(span[0]) and (span[0] < lo - 1e-6 or span[1] > hi + 1e-6):
                self.flag("travel", -1, 0, f"{axis.upper()} turns to {span[0]:g}..{span[1]:g}, outside its limits "
                                           f"{lo:g}..{hi:g}")

    def _arc_rule(self, file, line, move, start, end) -> None:
        u, v = {"G17": (0, 1), "G18": (2, 0), "G19": (1, 2)}[move.plane]
        c = move.centre
        r0 = math.hypot(start[u] - c[u], start[v] - c[v])
        r1 = math.hypot(end[u] - c[u], end[v] - c[v])
        if abs(r0 - r1) > max(0.005, 1e-4 * r0):
            self.flag("arc", file, line, f"the arc's end is {r1:.4f} mm from its centre and its start {r0:.4f} mm")
        full = math.hypot(end[u] - start[u], end[v] - start[v]) < 1e-9
        if r0 < 0.01 or (full and r0 < 0.05):
            self.flag("arc", file, line, f"a degenerate arc (radius {r0:.4f} mm{', a full circle' if full else ''})")

    def _tap_rule(self, file, line, move, st, start, end) -> None:
        tool = self.tool_shape()
        if move.cycle in ("G84", "G74"):
            want = "ccw" if move.cycle == "G74" else "cw"
            if st.spindle != want:
                self.flag("tap", file, line, f"{move.cycle} with the spindle {st.spindle} (it must run "
                                             f"{'M4' if want == 'ccw' else 'M3'})")
            if tool.type == "tap" and (tool.hand == "left") != (move.cycle == "G74"):
                self.flag("tap", file, line, f"{move.cycle} with a {tool.hand}-hand tap")
            if self.post == "fanuc" and not st.m29:
                self.flag("tap", file, line, "a Fanuc G84 without M29: the tap is fed without spindle sync")
            self._tap_feed(file, line, move, st, tool)
            return
        if move.cycle == "G33.1":
            want = "ccw" if tool.hand == "left" else "cw"
            if st.spindle != want:
                self.flag("tap", file, line, f"G33.1 with the spindle {st.spindle} for a {tool.hand}-hand tap")
            return
        if tool.type != "tap" or move.cycle is not None or start[2] is None or end[2] is None:
            return
        if start[2] == TOP or end[2] == TOP:
            return
        surface = self.material.stock_top if self.mode == "zmap" else 0.0
        hand = "ccw" if tool.hand == "left" else "cw"
        reverse = "cw" if hand == "ccw" else "ccw"
        if move.kind == "rapid":
            if st.tap_in and min(start[2], end[2]) < surface - self.tol:
                self.flag("tap", file, line, "the tap leaves the thread at rapid")
            st.tap_in = False
            return
        if end[2] < start[2] - 1e-9 and end[2] < surface:
            if st.spindle != hand:
                self.flag("tap", file, line, f"the tap feeds in with the spindle {st.spindle}")
            st.tap_in = True
            self._tap_feed(file, line, move, st, tool)
        elif end[2] > start[2] + 1e-9 and start[2] < surface:
            if st.spindle != reverse:
                self.flag("tap", file, line, "the tap feeds out without the spindle reversed")
            st.tap_in = end[2] < surface
            self._tap_feed(file, line, move, st, tool)

    def _tap_feed(self, file, line, move, st, tool) -> None:
        if tool.type != "tap" or not tool.pitch or not st.rpm:
            return
        want = st.rpm * tool.pitch
        if move.feed and abs(move.feed - want) > 0.02 * want:
            self.flag("tap", file, line, f"the tap feeds at {move.feed:g} mm/min; {st.rpm:g} rpm x "
                                         f"{tool.pitch:g} mm pitch is {want:g}")

    def _beam_rule(self, file, line, move, st, start, end, xy_moves) -> None:
        if self.post == "marlin" and move.s is not None:
            st.inline_s = float(move.s)
        on = st.beam or (self.post == "marlin" and st.inline_s > 0 and move.kind != "rapid")
        if move.kind == "rapid":
            # Strict on GRBL too: its laser mode ($32=1) keeps G0 dark, but a machine without it fires.
            if (st.beam and xy_moves) or (self.post == "marlin" and st.inline_s > 0 and xy_moves and move.s is None):
                self.flag("beam", file, line, "a rapid with the beam on")
            if self.kind == "plasma" and xy_moves and end[2] is not None and getattr(self, "_pierce_z", None) \
                    is not None and end[2] < self._pierce_z - 1e-6:
                self.flag("beam", file, line, f"the torch rapids across the sheet at Z{end[2]:g}, below its pierce "
                                              f"height Z{self._pierce_z:g}")
            return
        if st.beam and xy_moves:
            if self.kind in ("plasma", "waterjet") and not st.pierced:
                self.flag("beam", file, line, "the beam cuts with no pierce dwell after it came on")
            if self.kind == "plasma" and start[2] is not None:
                z_on = st.beam_z
                if z_on is None:
                    self.flag("beam", file, line, "the torch fired at an unknown height")
                elif start[2] != TOP and z_on <= start[2] + 1e-6:
                    self.flag("beam", file, line, f"the torch fired at Z{z_on:g}, not above its cut height "
                                                  f"Z{start[2]:g}")
                if z_on is not None and z_on != TOP:
                    self._pierce_z = max(getattr(self, "_pierce_z", -math.inf), z_on)
            st.pierced = True

    def _wire_mark(self, points, radius) -> None:
        if self.wire_mask is None:
            return
        step = 0.1
        r = int(math.ceil(radius / step))
        for p in points:
            i = int(round((p[0] - self.wire_lo[0]) / step))
            j = int(round((p[1] - self.wire_lo[1]) / step))
            self.wire_mask[max(0, i - r):i + r + 1, max(0, j - r):j + r + 1] = True

    def _wire_rule(self, file, line, points) -> None:
        if self.wire_mask is None:
            return
        step = 0.1
        for p in points:
            if not (self.wire_lo[0] < p[0] < self.wire_hi[0] and self.wire_lo[1] < p[1] < self.wire_hi[1]):
                continue
            i = int(round((p[0] - self.wire_lo[0]) / step))
            j = int(round((p[1] - self.wire_lo[1]) / step))
            if not self.wire_mask[min(i, self.wire_mask.shape[0] - 1), min(j, self.wire_mask.shape[1] - 1)]:
                self.flag("wire", file, line, f"a rapid drags the threaded wire through solid at ({p[0]:.2f}, "
                                              f"{p[1]:.2f})")
                return


def check(texts, **context) -> list[Finding]:
    """Every crash in one setup's posted program. ``texts``: the program, or its files in order (GRBL's one file
    per tool: each starts from scratch, the material carries on). Context: ``kind`` and ``post`` (required),
    ``stock`` (:class:`StockShape`), ``tools`` ({number: :class:`ToolShape`}), ``clearance`` and ``retract`` (WCS Z),
    ``travel`` ([X, Y, Z] mm, a lathe's [X, Z]), ``rotary_limits`` ({"a": (lo, hi)}), ``kinematics``,
    ``setup_rotary`` (a 3+2 setup's {"a": deg, ...}), ``fixtures`` ([(lo, hi)] part mm), ``diameter`` (a lathe's
    X words), ``options`` (the post's machine keys), ``cell_mm``, ``tol_mm``."""
    texts = [texts] if isinstance(texts, str) else list(texts)
    sim = _Sim(**context)
    for k, text in enumerate(texts):
        sim.run(k, text)
    sim.finish()
    return sim.findings


def context_from_cam(cam: dict, setup_id: str, *, job: dict | None = None, post: str | None = None) -> dict:
    """The :func:`check` context of one setup of a plan, from its result GLB's extras (``scenes[0].extras.cam``) and
    optionally the job (for fixtures and post options). ``post`` overrides the plan's post."""
    machine = cam["machine"]
    setup = next(s for s in cam["setups"] if s["id"] == setup_id)
    tools = {}
    for k, entry in enumerate(cam.get("tools", [])):
        shape = ToolShape.from_job(entry, k)
        tools[shape.number] = shape
    fixtures = []
    options = {}
    if job is not None:
        for raw in job.get("setups", []):
            if raw.get("id") == setup_id:
                boxes = raw.get("fixture", [])
                boxes = [boxes] if isinstance(boxes, dict) else boxes
                fixtures = [(b["min_mm"], b["max_mm"]) for b in boxes]
        options = {k: v for k, v in job.get("machine", {}).items()}
    rotary = {}
    orientation = setup.get("orientation")
    if isinstance(orientation, dict):
        rotary = {k[0]: float(v) for k, v in orientation.items() if v}
    heights = setup["heights"]
    return {
        "kind": machine["kind"], "post": post or machine.get("post"),
        "stock": StockShape.from_extras(cam["stock"], setup["matrix"]), "tools": tools,
        "clearance": heights["clearance"], "retract": heights["retract"], "travel": machine.get("travel_mm"),
        "rotary_limits": machine.get("rotary_limits_deg") or {}, "kinematics": machine.get("kinematics") or
        "ac_trunnion", "setup_rotary": rotary, "fixtures": fixtures, "diameter": machine.get("diameter_mode", True),
        "options": options,
    }


def check_plan(result, *, job: dict | None = None) -> list[tuple[str, Finding]]:
    """Every crash in a ``cam.plan`` result's posted files: ``[(setup id, finding), ...]``."""
    import json
    import struct
    from pathlib import Path

    data = Path(result.glb).read_bytes() if hasattr(result, "glb") else Path(result["glb"]).read_bytes()
    length = struct.unpack_from("<I", data, 12)[0]
    cam = json.loads(data[20:20 + length])["scenes"][0]["extras"]["cam"]
    posts = result.posts if hasattr(result, "posts") else result["posts"]
    out = []
    for setup in cam["setups"]:
        files = [Path(p["file"]).read_text(encoding="utf-8") for p in posts if p["setup"] == setup["id"]]
        for finding in check(files, **context_from_cam(cam, setup["id"], job=job)):
            out.append((setup["id"], finding))
    return out
