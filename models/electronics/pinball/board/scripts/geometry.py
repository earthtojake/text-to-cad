"""SHORT CIRCUIT's playfield board: every place the board takes from the design model, in one module.

The design model (`../../src`: `layout.py`, `playfield.py`) is the source of every number here: the outline,
the flipper pivots, the posts, the inserts, the sensor combs and the art. This module turns them into what
the board needs: the fixing holes under each part the board carries, the sensor combs as footprints (each
comb with a plated land at the end of each spine, where its net leaves for the inner layers), the LEDs at
the inserts and under the furniture, and the art clipped to what a fab can make.

Frames: the playfield frame (layout.py: mm, x across from the left edge, y up the field from the front
edge) and KiCad's (mm, y down), `kicad(x, y)` = layout.to_kicad. Plain data and shapely only: the library,
schematic and board scripts and the fit check import it.
"""
from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent                      # models/electronics/pinball/board
SRC = PROJECT.parent / "src"               # the design model
sys.path.insert(0, str(SRC))

from shapely import affinity  # noqa: E402
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box  # noqa: E402
from shapely.ops import split, unary_union  # noqa: E402

import layout as L  # noqa: E402
import playfield as P  # noqa: E402

ORIGIN = (40.0, 30.0)                      # the board's front-left corner sits at KiCad (40, 30 + BOARD_L)


def kicad(x: float, y: float) -> tuple[float, float]:
    return L.to_kicad(x, y, ORIGIN)


def playfield(kx: float, ky: float) -> tuple[float, float]:
    return (kx - ORIGIN[0], L.BOARD_L - (ky - ORIGIN[1]))


def kpoly(poly: Polygon) -> list[tuple[float, float]]:
    """A hole-free polygon's outline in KiCad's frame (the closing point dropped)."""
    return [kicad(x, y) for x, y in list(poly.exterior.coords)[:-1]]


# ============================================================================================ the rules
# JLCPCB standard 4-layer, 1 oz outer / 0.5 oz inner, ENIG, read from the pcb skill's manufacturing
# reference (jlcpcb.com/capabilities, 2026-11-04): 0.09 mm track/space (we keep 0.15), 0.15 mm min drill
# for vias (we keep 0.3), 0.2 mm copper to the routed edge (we keep 0.3).
CLEARANCE = 0.15
SIGNAL = 0.2
VIA_D, VIA_DRILL = 0.6, 0.3
EDGE_CLEARANCE = 0.3
HOLE_CLEARANCE = 0.25

# ============================================================================================ the outline


def outline() -> Polygon:
    """The board: the design model's rounded rectangle (parts.board_outline)."""
    return P.rounded_rect(0, 0, L.BOARD_W, L.BOARD_L, L.BOARD_CORNER)


# ============================================================================================ fixing holes

@dataclass(frozen=True)
class Hole:
    name: str
    x: float
    y: float
    d: float
    fixes: str          # the part it fixes, as the design model names it
    why: str
    ref: str = ""       # its designator on the schematic and the board: H1, H2, ...


def holes() -> list[Hole]:
    """Every hole through the board. The flipper shafts' bores are the design model's (parts.playfield_board,
    6.0 mm); the rest fix the parts the board carries from below (M2, 2.2 mm clearance), each under its part."""
    out = []
    for side, (x, y) in L.PIVOTS.items():
        out.append(Hole(f"H_PIVOT_{side[0].upper()}", x, y, 6.0, f"{side}_shaft", "flipper shaft bore (CAD: r 3.0)"))
    for name, (x, y) in L.BUMPERS.items():
        for k, dx in enumerate((-3.6, 3.6)):
            out.append(Hole(f"H_{name}_{k + 1}", x + dx, y, 2.2, f"bumper_{name}_post",
                            "M2 self-tapping screw from below into the post (its LED bore at the centre)"))
    for side in ("left", "right"):
        for k, (x, y) in enumerate(P.sling_posts(side)):
            out.append(Hole(f"H_SLING_{side[0].upper()}{k + 1}", x, y, 2.2, f"sling_{side}_post_{k + 1}",
                            "M2 screw from below into the 4 mm hex standoff"))
    for side, (g0, g1) in (("left", L.GUIDE_L), ("right", L.GUIDE_R)):
        out.append(Hole(f"H_LANEPOST_{side[0].upper()}", (g0 + g1) / 2, L.LANE_TOP_Y, 2.2, f"lane_post_{side}",
                        "M2 screw from below into the 4 mm hex standoff"))
    for side, x in (("L", L.RAIL_W / 2), ("R", L.BOARD_W - L.RAIL_W / 2)):
        for k, y in enumerate((40.0, 80.0, 120.0, 160.0, 196.0)):
            out.append(Hole(f"H_RAIL_{side}{k + 1}", x, y, 2.2, f"rail_{'left' if side == 'L' else 'right'}",
                            "M2 screw from below into a heat-set insert in the rail"))
    for k, x in enumerate((12.0, 34.0, 78.0)):
        out.append(Hole(f"H_LOCKDOWN_{k + 1}", x, L.LOCKDOWN_D / 2, 2.2, "lockdown_bar",
                        "M2 screw from below into a heat-set insert in the lockdown bar"))
    for k, (x, y) in enumerate(((10.0, 212.0), (102.0, 212.0), (10.0, 228.0), (102.0, 228.0))):
        out.append(Hole(f"H_WEDGE_{k + 1}", x, y, 2.2, "backbox_wedge",
                        "M2 screw from below into a heat-set insert in the backbox's wedge"))
    return [Hole(h.name, h.x, h.y, h.d, h.fixes, h.why, f"H{k + 1}") for k, h in enumerate(out)]


# ============================================================================================ the sensors

FINGER, PITCH = P.FINGER, P.PITCH
LAND_PAD, LAND_DRILL = 0.7, 0.3            # a comb's plated land: its net's way to the inner layers


@dataclass
class Sensor:
    name: str          # playfield.sensors()' key
    ref: str           # its switch's designator (layout.SWITCHES)
    net: str           # the comb's own net, as the art names it (SENSE_*)
    anchor: tuple      # the footprint's origin, playfield frame
    sense: Polygon     # the SENSE comb
    gnd: Polygon       # the GND comb
    land_sense: tuple  # the lands' centres, playfield frame
    land_gnd: tuple

    @property
    def line(self) -> str:
        """Its GPIO's net, behind the series resistor (the comb's own net is exposed metal)."""
        return "IN_" + self.net.removeprefix("SENSE_")


def _axis_y_lands(x0, y0, x1, y1):
    n = int((y1 - y0 - FINGER) / PITCH) + 1
    ys0 = y0 + (y1 - y0 - (n - 1) * PITCH) / 2
    return (x0 + 0.2, ys0 - 0.45), (x1 - 0.2, ys0 - 0.45)


def _axis_x_lands(x0, y0, x1, y1):
    n = int((x1 - x0 - FINGER) / PITCH) + 1
    xs0 = x0 + (x1 - x0 - (n - 1) * PITCH) / 2
    return (xs0 - 0.4, y0 + 0.2), (xs0 - 0.4, y1 - 0.2)


def _lands():
    """Each comb's two lands, at the end of its spines (the comb parameters are playfield.sensors()')."""
    out = {}
    y0, y1 = L.TOP_LANE_Y[0] + 2.0, L.TOP_LANE_Y[0] + 13.0
    for name, x in L.TOP_LANES.items():
        out[f"LANE_{name}"] = _axis_y_lands(x - 4.3, y0, x + 4.3, y1)
    for name, (a, b) in (("OUT_L", L.OUTLANE_L), ("IN_L", L.INLANE_L), ("IN_R", L.INLANE_R), ("OUT_R", L.OUTLANE_R)):
        x = (a + b) / 2
        out[name] = _axis_y_lands(x - 4.3, 66.0, x + 4.3, 76.0)
    for name, (x, y) in L.BUMPERS.items():
        out[f"BUMPER_{name}"] = ((x + 7.6 * math.cos(math.radians(225)), y + 7.6 * math.sin(math.radians(225))),
                                 (x + 12.4 * math.cos(math.radians(45)), y + 12.4 * math.sin(math.radians(45))))
    for name, y in L.TARGETS.items():
        f = L.TARGET_FACE_X
        out[f"TARGET_{name}"] = _axis_x_lands(f + 1.6, y - 5.0, f + 6.6, y + 5.0)
    for side in ("left", "right"):
        (ax, ay), (bx, by), (nx, ny) = P.sling_active_line(side)
        length = math.hypot(bx - ax, by - ay)
        ux, uy = (bx - ax) / length, (by - ay) / length
        mx, my = (ax + bx) / 2, (ay + by) / 2
        a, b = _axis_y_lands(-length / 2 + 3.5, 2.4, length / 2 - 12.0, 4.8)
        tr = lambda p: (mx + ux * p[0] + nx * p[1], my + uy * p[0] + ny * p[1])  # noqa: E731
        out[f"SLING_{side[0].upper()}"] = (tr(a), tr(b))
    out["ORBIT"] = _axis_y_lands(L.FIELD_X0 + 1.4, 140.0, L.FIELD_X0 + 10.6, 150.0)
    x0, x1 = L.SHOOTER_LANE
    out["SHOOTER"] = _axis_y_lands(x0 + 1.0, L.BALL_READY_Y - 3.6, x1 - 1.0, L.BALL_READY_Y + 3.6)
    out["DRAIN"] = _axis_x_lands(L.CENTER_X + 12.0, 14.0, L.CENTER_X + 20.0, 24.0)
    return out


def sensors() -> list[Sensor]:
    combs = P.sensors()
    lands = _lands()
    out = []
    for name, ref in L.SWITCHES.items():
        nets = combs[name]
        net = next(n for n in nets if n != "GND")
        sense, gnd = nets[net], nets["GND"]
        ls, lg = lands[name]
        for land, own, other, what in ((ls, sense, gnd, "SENSE"), (lg, gnd, sense, "GND")):
            disc = Point(land).buffer(LAND_PAD / 2, quad_segs=16)
            assert disc.intersects(own), f"{name}: the {what} land misses its comb"
            assert disc.distance(other) >= 0.2, f"{name}: the {what} land is {disc.distance(other):.2f} from the other net"
        c = unary_union([sense, gnd]).centroid
        out.append(Sensor(name, ref, net, (round(c.x, 3), round(c.y, 3)), sense, gnd, ls, lg))
    return out


# ============================================================================================ the LEDs

@dataclass(frozen=True)
class Led:
    ref: str
    what: str          # what it lights
    side: str          # "F" or "B"
    x: float
    y: float
    rot: float         # KiCad orientation, degrees
    package: str       # "SK6812MINI-E" (reverse mount, in a cut-out under an insert) or "WS2812B-2020"
    cap: tuple         # its 100 nF: (x, y, rot, side)


def _sling_centroid(side):
    pts = P.sling_posts(side)
    return (sum(p[0] for p in pts) / 3, sum(p[1] for p in pts) / 3)


def leds_unordered():
    """Every LED with its place: the inserts' (art.leds, under the board in a cut-out), the furniture's (on top,
    under a bumper's bore, a sling's plate, a target's post, as parts.py puts them) and the underglow (under
    the board's long edges, facing into the engine room)."""
    art = P.build_art()
    out = []
    for name, (x, y) in art.leds.items():
        # its capacitor beside it, toward the board's back (+y), clear of the cut-out's pads
        out.append(("insert", f"INSERT_{name}", "B", x, y, 0.0, "SK6812MINI-E", (x, y + 2.75, 0.0, "B")))
    for name, (x, y) in L.BUMPERS.items():
        out.append(("bumper", f"BUMPER_{name}", "F", x, y, 0.0, "WS2812B-2020", (x, y, 0.0, "B")))
    for side in ("left", "right"):
        x, y = _sling_centroid(side)
        # the sling's 100 nF stands beside it on top (the flipper's bracket fills the underside there)
        out.append(("sling", f"SLING_{side[0].upper()}", "F", x, y, 0.0, "WS2812B-2020", (x, y - 2.2, 0.0, "F")))
    for name, y in L.TARGETS.items():
        x = L.TARGET_FACE_X - 3.4
        out.append(("target", f"TARGET_{name}", "F", x, y, 90.0, "WS2812B-2020", (x + 1.5, y + 2.6, 0.0, "B")))
    for i in range(6):
        for side, x in (("L", 5.0), ("R", L.BOARD_W - 5.0)):
            y = 34.0 + 30.0 * i
            out.append(("underglow", f"GLOW_{side}{i + 1}", "B", x, y, 0.0, "WS2812B-2020", (x, y + 2.4, 0.0, "B")))
    return out


# the level shifter (U7) stands by U1's LED_DATA pin, under the backbox; the chain starts beside it, at the right edge's
# underglow (the shortest tour from here)
U7_AT = (104.0, 202.0)
CHAIN_START = (106.0, 196.0)


def leds() -> list[Led]:
    """The LEDs in chain order (data from the MCU through every LED once): a short tour from the start,
    nearest first, then untangled (2-opt). LED1 is first in the chain, LED38 last."""
    items = leds_unordered()
    pts = [(it[3], it[4]) for it in items]
    order, left = [], list(range(len(items)))
    at = CHAIN_START
    while left:
        k = min(left, key=lambda i: math.dist(at, pts[i]))
        order.append(k)
        left.remove(k)
        at = pts[k]

    def length(o):
        return math.dist(CHAIN_START, pts[o[0]]) + sum(math.dist(pts[a], pts[b]) for a, b in zip(o, o[1:]))
    improved = True
    while improved:                          # the first LED stays the one nearest the start
        improved = False
        for i in range(1, len(order) - 1):
            for j in range(i + 2, len(order) + 1):
                new = order[:i] + order[i:j][::-1] + order[j:]
                if length(new) < length(order) - 1e-9:
                    order, improved = new, True
    out = []
    for n, k in enumerate(order, start=1):
        kind, what, side, x, y, rot, pkg, cap = items[k]
        out.append(Led(f"LED{n}", what, side, round(x, 3), round(y, 3), rot, pkg, cap))
    return out


# ============================================================================================ the art

def _holefree(geom) -> list[Polygon]:
    """Polygons without holes (a board graphic has none): each holed polygon cut through its holes."""
    out = []
    todo = [g for g in getattr(geom, "geoms", [geom]) if isinstance(g, Polygon) and not g.is_empty]
    while todo:
        poly = todo.pop()
        if not poly.interiors:
            out.append(poly)
            continue
        hx = Polygon(poly.interiors[0]).representative_point().x
        minx, miny, maxx, maxy = poly.bounds
        pieces = split(poly, LineString([(hx, miny - 1), (hx, maxy + 1)]))
        todo += [g for g in pieces.geoms if isinstance(g, Polygon) and g.area > 1e-6]
    return out


def led_cutout(x, y) -> Polygon:
    """The SK6812MINI-E's cut-out, KiCad's stock footprint: 3.4 x 3.0 mm, its corners relieved round (the arcs'
    far points included, so the polygon holds the whole cut-out)."""
    a, b, c, d, e, f = 1.743934, 0.856655, 1.056655, 1.543934, 1.670711, 1.470711
    pts = [(-a, -b), (-e, -f), (-c, -d), (c, -d), (e, -f), (a, -b), (a, b), (e, f), (c, d), (-c, d), (-e, f), (-a, b)]
    return Polygon([(x + px, y + py) for px, py in pts])


@dataclass
class BoardArt:
    copper_gnd: list        # hole-free polygons on F.Cu, net GND (they touch a GND comb or a stitching via)
    copper_free: list       # hole-free polygons on F.Cu with no net (the ornament no ground reaches)
    dots: list              # (x, y, d): gold dots, F.Cu with no net
    mask: list              # hole-free polygons opened in F.Mask (the gold, the windows)
    silk: list              # (x, y, d): white dots on F.SilkS
    vias: list              # (x, y, diameter, drill): stitching vias, GND, open on top
    windows: dict           # insert name -> its window polygon (no copper, no mask)
    report: dict


def board_art(keepout_holes=True, avoid_top=None, avoid_through=None) -> BoardArt:
    """The art from playfield.build_art(), as the board makes it, every change measured in `report`:
    - the combs are footprints (sensors()), not art; each comb's lands keep the ornament 1.2 mm off, as the
      combs themselves do (playfield.ISOLATE);
    - each stitching via the art draws (a ring on the ornament) is a real via to the ground planes, where its
      whole ring survived the art's own clipping; the rest stay rings of copper;
    - each insert's window takes in its LED's cut-out where the cut-out is larger (the lamps, the bonus ladder),
      and its gold ring is drawn round the two;
    - copper keeps 0.3 mm from the edge and 0.4 mm from every hole;
    - `avoid_top` (the pads on the top copper, from the placed board) keeps the ornament off them, `avoid_through`
      (every pad and courtyard on the underside, every plated hole) keeps a stitching via off them: a via there
      stays a ring of copper."""
    art = P.build_art()
    sens = sensors()
    report = {}
    combs = unary_union([s.sense for s in sens] + [s.gnd for s in sens])
    lands_sense = unary_union([Point(s.land_sense).buffer(LAND_PAD / 2, quad_segs=12) for s in sens])
    gnd_combs = unary_union([s.gnd for s in sens] + [Point(s.land_gnd).buffer(LAND_PAD / 2, quad_segs=12) for s in sens])

    # the windows: the art's, grown to the LED's cut-out where that is larger
    windows = {}
    grown = 0
    for name, win in art.inserts.items():
        x, y = art.leds[name]
        cut = led_cutout(x, y).buffer(0.12, quad_segs=8)   # the arcs bulge past the polygon's chords
        if not win.contains(cut):
            grown += 1
        windows[name] = win.union(cut)
    report["windows grown to their LED's cut-out"] = grown

    # the ornament (GND gold, not the combs), less the art's own window rings (redrawn below)
    orn = unary_union([p for p, n in art.gold if n == "GND"]).difference(combs)
    old_rings = unary_union([w.buffer(0.75, join_style=2).difference(w.buffer(0.3, join_style=2))
                             for w in art.inserts.values()])
    orn = orn.difference(old_rings.buffer(0.01))
    rings = unary_union([w.buffer(0.75, quad_segs=16, join_style=2).difference(w.buffer(0.3, quad_segs=16, join_style=2))
                         for w in windows.values()])
    orn = unary_union([orn, rings])

    # what copper must keep away from
    keep = [lands_sense.buffer(P.ISOLATE, quad_segs=8)]
    if keepout_holes:
        keep += [Point(h.x, h.y).buffer(h.d / 2 + 0.4, quad_segs=12) for h in holes()]
    keep.append(outline().exterior.buffer(L.BOARD_CORNER * 0 + EDGE_CLEARANCE + 0.05))
    keep.append(unary_union(list(windows.values())).buffer(0.3, join_style=2))
    if avoid_top is not None:
        keep.append(avoid_top.buffer(0.3))
    keep = unary_union(keep)
    before = orn.area
    orn = orn.difference(keep)
    orn = orn.buffer(-0.03, join_style=2).buffer(0.03, join_style=2)   # no slivers from the clipping
    report["ornament area clipped, mm2"] = round(before - orn.area, 2)

    # the stitching vias: the art's rings (0.18/0.42 on the pinstripe, 0.2/0.45 by the bonus ladder)
    vias = []
    edge = P.field_region().buffer(-2.0, quad_segs=P.RES, join_style=1).boundary
    candidates = [(edge.interpolate(k * 6.0 + 3.0).coords[0], 0.42, 0.18) for k in range(int(edge.length / 6.0))]
    candidates += [((x + dx, y), 0.45, 0.2) for (x, y) in L.BONUS_INSERTS for dx in (-4.4, 4.4)]
    dropped = 0
    for (x, y), ro, ri in candidates:
        ring = Point(x, y).buffer(ro, quad_segs=16).difference(Point(x, y).buffer(ri, quad_segs=16))
        clear = avoid_through is None or avoid_through.distance(Point(x, y)) > ro + 0.2
        clear = clear and all(math.dist((x, y), (vx, vy)) > 2.0 for vx, vy, *_ in vias)
        if clear and orn.intersection(ring).area >= 0.97 * ring.area and keep.distance(Point(x, y)) > ro + 0.1:
            vias.append((round(x, 4), round(y, 4), round(2 * ro, 3), round(2 * ri, 3)))
        else:
            dropped += 1
    report["stitching vias"] = len(vias)
    report["stitching rings left as copper (clipped by the art)"] = dropped

    # nets: a piece touching (or within 0.2 mm of) a GND comb, a GND land or a via is GND; the rest float
    via_discs = unary_union([Point(x, y).buffer(d / 2, quad_segs=12) for x, y, d, _ in vias])
    pieces = [g for g in getattr(orn, "geoms", [orn]) if isinstance(g, Polygon) and g.area > 1e-4]
    gnd, free = [], pieces
    reach = unary_union([gnd_combs, via_discs])
    bridged = 0
    while True:                        # GND spreads through every piece within 0.2 mm of GND copper; a piece that does
        near = [g for g in free if g.distance(reach) < 0.2]   # not quite touch is bridged to it (a gap is no connection)
        if not near:
            break
        free = [g for g in free if g.distance(reach) >= 0.2]
        joined = []
        for g in near:
            d = g.distance(reach)
            if d > 1e-4:
                g = g.union(g.buffer(d + 0.06, quad_segs=4).intersection(reach.buffer(d + 0.06, quad_segs=4)))
                bridged += 1
            joined.append(g)
        gnd += joined
        reach = unary_union([reach, *joined])
    report["ornament pieces bridged to ground across a clipping gap"] = bridged
    report["ornament pieces on GND"] = len(gnd)
    report["ornament pieces floating"] = len(free)
    # a via's own ring is the via: its copper comes out of the ornament
    via_holes = unary_union([Point(x, y).buffer(dr / 2, quad_segs=12) for x, y, _, dr in vias])
    gnd = [g.difference(via_holes) for g in gnd]

    dots = [(x, y, d) for x, y, d, _ in art.gold_dots]
    keep_dots = keep.buffer(0.0)
    dots = [(x, y, d) for x, y, d in dots if keep_dots.distance(Point(x, y)) > d / 2]
    report["gold dots"] = len(dots)

    gold_all = unary_union(gnd + free + [Point(x, y).buffer(d / 2, quad_segs=8) for x, y, d in dots]
                           + [combs])
    mask = unary_union([gold_all.buffer(0.05, quad_segs=8, join_style=1), *windows.values(),
                        *[Point(x, y).buffer(d / 2 + 0.05, quad_segs=12) for x, y, d, _ in vias]])
    silk = [(x, y, d) for x, y, d in art.silk_dots if keep.distance(Point(x, y)) > d / 2 + 0.1
            and mask.distance(Point(x, y)) > d / 2 + 0.03]
    report["silk dots"] = len(silk)
    return BoardArt(_holefree(unary_union(gnd)), _holefree(unary_union(free)), dots, _holefree(mask), silk,
                    vias, windows, report)


# ============================================================================================ the parts' places

FIDUCIALS_TOP = [(f"FID{k + 1}", x, y) for k, (x, y) in enumerate(L.FIDUCIALS)]
FIDUCIALS_BOTTOM = [("FID4", 16.0, 14.0), ("FID5", 96.0, 196.0), ("FID6", 96.0, 40.0)]

FLIPPER_BUTTON_Y = L.FLIPPER_Y - 20.0      # the rails' buttons (parts.buttons)
START_AT = (L.BOARD_W / 2, L.LOCKDOWN_D / 2 - 0.6)


# ============================================================================================ the RP2040's pins

# U1, on the board's underside, in the strip behind the arch: no art above it, so its vias are free (the top lanes'
# combs left no room for them under parts.underside_parts' stand-in at y 158).
MCU_AT = (80.0, 212.0)
MCU_ROT = 180.0                            # its two GPIO-rich sides left and right, each with a clear run to the
                                           # field; QSPI and USB toward the back edge, the flash behind it

# Pins the silicon decides: I2C1 SDA/SCL (GP18/19), PIO's I2S side-set pair (BCLK, LRCLK consecutive), an ADC input.
GPIO_FIXED = {"I2C_SDA": 18, "I2C_SCL": 19, "I2S_BCLK": 20, "I2S_LRCLK": 21, "I2S_DIN": 22, "VBUS_SENSE": 29}
# QFN-56 pad numbers of GPIO0..29 (MCU_RaspberryPi:RP2040)
GPIO_PAD = {**{i: 2 + i for i in range(8)}, **{i: 3 + i for i in range(8, 16)}, **{i: 11 + i for i in range(16, 22)},
            **{i: 12 + i for i in range(22, 30)}}


def qfn56_pad(number: int) -> tuple[float, float]:
    """A pad's centre on the library footprint (y down): 14 a side at 0.4 mm, the row at 3.4375 mm."""
    k = (number - 1) % 14
    side = (number - 1) // 14
    s = -2.6 + 0.4 * k
    return {0: (-3.4375, s), 1: (s, 3.4375), 2: (3.4375, -s), 3: (-s, -3.4375)}[side]


def on_board(local, at, rot, side):
    """A footprint's local point (y down) in the playfield frame, placed at `at` (playfield), KiCad orientation
    `rot`, on side "F" or "B" (the back mirrors top to bottom, then turns: pcb skill's placement reference)."""
    lx, ly = local
    if side == "B":
        ly = -ly
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    kx, ky = lx * c + ly * s, -lx * s + ly * c         # KiCad's frame, y down, counter-clockwise as seen
    return (at[0] + kx, at[1] - ky)                    # the playfield's y runs the other way


def gpio_destinations() -> dict[str, tuple[float, float]]:
    """Where each free signal has to go, playfield frame: its comb's land, its button, its driver."""
    out = {s.line: s.land_sense for s in sensors()}
    out["BTN_FLIP_L"] = (1.6, FLIPPER_BUTTON_Y)
    out["BTN_FLIP_R"] = (L.BOARD_W - 1.6, FLIPPER_BUTTON_Y)
    out["BTN_START"] = START_AT
    out["COIL_L"] = (L.PIVOTS["left"][0] + 6.0, 88.0)
    out["COIL_R"] = (L.PIVOTS["right"][0] - 6.0, 88.0)
    out["LED_DATA"] = U7_AT
    return out


def gpio_map() -> dict[str, int]:
    """Every signal's GPIO. The free ones are matched to pins by least total travel, a pin on the far side of
    the package costing its turn round it (so the fan-out leaves the RP2040 in the order it arrives)."""
    from scipy.optimize import linear_sum_assignment
    dests = gpio_destinations()
    names = sorted(dests)
    free = [g for g in range(30) if g not in GPIO_FIXED.values()]
    if len(names) != len(free):
        raise SystemExit(f"{len(names)} signals for {len(free)} free GPIOs")
    cost = []
    centre = MCU_AT
    for name in names:
        row = []
        dx, dy = dests[name]
        for g in free:
            px, py = on_board(qfn56_pad(GPIO_PAD[g]), MCU_AT, MCU_ROT, "B")
            ox, oy = px - centre[0], py - centre[1]
            n = math.hypot(ox, oy)
            want = math.atan2(dy - py, dx - px)
            have = math.atan2(oy / n, ox / n)
            turn = abs((want - have + math.pi) % (2 * math.pi) - math.pi)
            row.append(math.dist((px, py), (dx, dy)) + 25.0 * turn)
        cost.append(row)
    rows, cols = linear_sum_assignment(cost)
    out = dict(GPIO_FIXED)
    for i, j in zip(rows, cols):
        out[names[i]] = free[j]
    return out


# U1's power pins: each goes inward, under the package's edge, to a via in the ring between its pads and its exposed
# pad, with its capacitor on the board's other side, straight over it (behind the arch, under the backbox's wedge: no
# art there). (name, pins, side, lateral of its via, net, capacitor); side is the way outward: back +y, front -y, left -x, right +x.
U1_POWER = [("back", (43, 44), -2.6, "+3V3", "C27", -2.6), ("back", (45,), -1.4, "+1V1", "C29", -1.6),
            ("back", (48, 49), -0.6, "+3V3", "C25", -0.6), ("back", (50,), 0.2, "+1V1", "C31", 0.4),
            # pins 22 and 23 (3V3, 1V1) are neighbours: their vias step inward and apart, either side
            ("front", (22,), 0.25, "+3V3", "C22", 0.6, 2.2), ("front", (23,), -0.9, "+1V1", "C30", -0.6, 2.2),
            ("left", (33,), -1.0, "+3V3", "C23", -1.0),
            # pin 42 shares pins 43/44's via at the corner; its capacitor stands a little along, clear of C27
            ("left", (42,), None, "+3V3", "C24", 1.9),
            # pin 1's via steps a pad along, clear of QSPI_SS (pin 56) round the corner
            ("right", (1,), 2.2, "+3V3", "C20", 2.6), ("right", (10,), -1.0, "+3V3", "C21", -1.0)]
U1_VIA_R, U1_CAP_R = 2.5, 3.48             # the ring via, the capacitor's centre, from U1's centre
U1_ISLAND = 5.0                            # the In2.Cu 3V3 island under U1 and the F.Cu ground over it: a square this half-size
OUTWARD = {"back": (0, 1), "front": (0, -1), "left": (-1, 0), "right": (1, 0)}


def u1_point(side, lateral, radial):
    """A point in U1's frame, playfield mm: `radial` out along its side, `lateral` across (x for back/front, y for left/right)."""
    ox, oy = OUTWARD[side]
    if ox:
        return (MCU_AT[0] + ox * radial, MCU_AT[1] + lateral)
    return (MCU_AT[0] + lateral, MCU_AT[1] + oy * radial)


def port_of(gpio: int):
    """A GPIO's port in U1's fan-out (routes.u1_stubs): its side, its lateral offset, its index along the side."""
    n = GPIO_PAD[gpio]
    px, py = on_board(qfn56_pad(n), MCU_AT, MCU_ROT, "B")
    dx, dy = px - MCU_AT[0], py - MCU_AT[1]
    if abs(dx) > abs(dy):
        side, s0 = ("right" if dx > 0 else "left"), dy
    else:
        side, s0 = ("back" if dy > 0 else "front"), dx
    k = (n - 1) % 14
    return side, s0 + math.copysign(abs(k - 6.5) * 0.4, s0), k


USB_ESD = (53.5, 223.5)                    # U4, on the USB pair


def clear_spot(near, taken, keep, size=(3.6, 2.0)):
    """A free place for a small part as near `near` as may be: octants at growing radius, off everything in `taken`
    (shapely geometry) and `keep`. The part's own box is `size`."""
    w, h = size
    for r in (2.2, 2.8, 3.4, 4.0, 4.8, 5.6, 6.5, 7.5, 8.5, 10.0, 11.5, 13.0, 14.5, 16.0):
        for k in range(8):
            a = math.radians(45.0 * k)
            x, y = near[0] + r * math.cos(a), near[1] + r * math.sin(a)
            b = box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)
            if not b.intersects(keep) and not b.intersects(taken) and outline().buffer(-1.0).contains(b):
                return (round(x, 2), round(y, 2))
    raise SystemExit(f"no room near {near}")


def part_places() -> dict[str, tuple]:
    """Every part but the LEDs and combs: (x, y, KiCad orientation, side), playfield frame. The underside's
    groups sit where parts.underside_parts drew them: the RP2040 under the top lanes, the power stage by the
    USB-C at the back edge, a coil driver by each solenoid's back end."""
    cx = 49.7
    at = {}
    # --- the RP2040, its flash and crystal, on the underside
    at["U1"] = (*MCU_AT, MCU_ROT, "B")
    at["U2"] = (cx + 16.6, 157.0, 0.0, "B")     # the flash, its pin 1 row facing U1's QSPI ports
    at["Y1"] = (cx - 12.6, 161.8, 0.0, "B")
    at["R12"] = (cx - 9.2, 162.6, 0.0, "B")     # XOUT's 1k
    at["C33"] = (cx - 14.0, 158.8, 0.0, "B")
    at["C34"] = (cx - 12.3, 164.8, 0.0, "B")
    # USB's 27 ohms, in line with their ports, then away to the connector
    at["R10"] = (cx + 11.9, 165.8, 0.0, "B")
    at["R11"] = (cx + 13.9, 165.0, 0.0, "B")
    # decoupling at the package's corners and beyond its fan-out (its ports stand 8 mm from the centre)
    at["C20"] = (cx + 5.5, 157.3, 0.0, "B")     # IOVDD 1
    at["C21"] = (cx - 5.5, 157.3, 0.0, "B")     # IOVDD 10
    at["C22"] = (cx - 5.6, 168.9, 0.0, "B")     # IOVDD 22
    at["C30"] = (cx - 7.8, 171.0, 0.0, "B")     # DVDD 23
    at["C23"] = (cx - 7.8, 172.4, 0.0, "B")     # IOVDD 33
    at["C24"] = (cx + 7.0, 172.4, 0.0, "B")     # IOVDD 42
    at["C25"] = (cx + 12.0, 163.4, 0.0, "B")    # IOVDD 49
    at["C26"] = (cx + 14.0, 163.4, 0.0, "B")    # USB_VDD 48
    at["C31"] = (cx + 12.0, 162.4, 0.0, "B")    # DVDD 50
    at["C27"] = (cx + 5.6, 168.9, 0.0, "B")     # ADC_AVDD 43
    at["C28"] = (cx + 11.9, 168.7, 0.0, "B")    # VREG_VIN 44, 1 uF
    at["C29"] = (cx + 11.9, 170.3, 0.0, "B")    # VREG_VOUT 45, 1 uF
    at["C32"] = (cx + 21.0, 153.8, 0.0, "B")    # the flash's 100 nF
    at["R13"] = (cx + 13.4, 152.4, 90.0, "B")   # BOOTSEL's 1k, on the flash's ~CS
    at["SW1"] = (cx + 26.0, 165.0, 0.0, "B")    # BOOTSEL
    at["SW2"] = (cx - 21.0, 168.0, 0.0, "B")    # RESET
    at["TP1"] = (cx - 13.0, 178.0, 0.0, "B")    # SWCLK
    at["TP2"] = (cx - 9.0, 178.0, 0.0, "B")     # SWDIO
    at["TP3"] = (cx - 5.0, 178.0, 0.0, "B")     # 3V3
    at["TP4"] = (cx - 1.0, 178.0, 0.0, "B")     # GND
    at["R14"] = (cx - 3.2, 175.5, 90.0, "B")    # I2C pull-ups
    at["R15"] = (cx - 1.7, 175.5, 90.0, "B")
    # the group's offsets above were drawn round (cx, 163): turned a quarter turn with U1, and moved
    for ref in ("U2", "Y1", "R12", "C33", "C34", "C26", "C28", "C32", "R13"):
        x, y, rot, side = at[ref]
        ox, oy = x - cx, y - 163.0
        at[ref] = (MCU_AT[0] - oy, MCU_AT[1] + ox, (rot + 90.0) % 360, side)
    # the crystal past the front fan-out's vias (its lanes drop to In2.Cu in the strip between)
    at["Y1"] = (MCU_AT[0] + 1.2, MCU_AT[1] - 16.2, 0.0, "B")
    at["C34"] = (MCU_AT[0] - 2.4, MCU_AT[1] - 16.2, 90.0, "B")
    at["C33"] = (MCU_AT[0] + 4.8, MCU_AT[1] - 16.2, 90.0, "B")
    at["R12"] = (MCU_AT[0] + 1.2, MCU_AT[1] - 13.0, 0.0, "B")
    at["C28"] = (MCU_AT[0] - 9.6, MCU_AT[1] + 7.6, 0.0, "B")   # VREG_VIN's 1 uF, at the corner
    at["C26"] = (MCU_AT[0] + 9.6, MCU_AT[1] + 7.6, 0.0, "B")   # a second 100 nF on the 3V3 island
    # the USB resistors in line with their ports, turned so pad 2 faces U1
    at["R10"] = (MCU_AT[0] - 2.8, MCU_AT[1] + 9.7, 270.0, "B")
    at["R11"] = (MCU_AT[0] - 2.0, MCU_AT[1] + 11.6, 270.0, "B")
    # each power pin's capacitor, on the other side of the board, over its via (pad 1 the supply, nearest U1; pad 2 into
    # the ground poured over U1 on the top copper)
    rot_top = {"back": 90.0, "front": 270.0, "left": 180.0, "right": 0.0}
    for side, pins, lat, net, cap, cap_lat, *_ in U1_POWER:
        x, y = u1_point(side, cap_lat, U1_CAP_R)
        at[cap] = (round(x, 3), round(y, 3), rot_top[side], "F")
    at["SW1"] = (96.0, 229.0, 0.0, "B")         # BOOTSEL
    at["SW2"] = (96.0, 205.5, 0.0, "B")         # RESET
    for k, ref in enumerate(("TP1", "TP2", "TP3", "TP4")):
        at[ref] = (88.0 + 3.5 * k, 199.0, 0.0, "B")  # SWCLK, SWDIO, 3V3, GND
    at["R14"] = (66.0, 205.0, 90.0, "B")        # I2C pull-ups
    at["R15"] = (67.5, 205.0, 90.0, "B")
    # --- tilt and sound, off the fan-out's left, by their I2C and I2S pins
    at["U9"] = (60.0, 203.0, 0.0, "B")
    at["C40"] = (63.8, 203.0, 90.0, "B")
    at["C41"] = (56.4, 203.0, 90.0, "B")
    at["U8"] = (60.0, 213.0, 0.0, "B")
    at["C70"] = (64.4, 214.0, 90.0, "B")
    at["C71"] = (60.0, 216.8, 0.0, "B")
    at["R40"] = (56.6, 216.8, 0.0, "B")
    at["J5"] = (60.0, 220.5, 0.0, "B")         # the speaker's pads, by the amplifier
    at["J4"] = (49.5, 199.2, 0.0, "B")         # the backbox link, by the tilt sensor's I2C and the amplifier
    at["U2"] = (83.5, 228.0, at["U2"][2], "B")  # the flash, over U1's QSPI pins, past the ends of their corridors
    at["C32"] = (85.4, 234.0, 0.0, "B")        # its 100 nF, at its VCC pin
    # --- the LED chain's level shifter, between the MCU and the chain's start
    at["U7"] = (*U7_AT, 0.0, "B")              # its input toward U1, its output toward LED1
    at["C50"] = (U7_AT[0] + 2.0, U7_AT[1] - 2.3, 0.0, "B")     # at its VCC pin
    at["R20"] = (U7_AT[0] + 3.05, U7_AT[1] + 0.95, 0.0, "B")    # 33 ohm, at its output
    # --- the power stage at the back edge
    at["J1"] = (L.CENTER_X, L.BOARD_L - 3.65, 0.0, "B")   # its mating face on the board's back edge
    at["U4"] = USB_ESD + (0.0, "B")             # the USB pair runs straight through it (routes.usb_pair)
    at["F1"] = (cx - 11.5, 226.5, 0.0, "B")
    # the PD trigger, on the connector's side of the USB pair, by its CC pins
    at["U3"] = (60.5, 231.2, 0.0, "B")
    at["C1"] = (60.5, 227.3, 0.0, "B")
    at["R2"] = (57.2, 227.3, 0.0, "B")
    at["R3"] = (65.3, 231.2, 90.0, "B")
    # the buck: input capacitors at VIN and GND, the inductor beside SW, the divider at VFB
    at["U5"] = (24.0, 222.0, 0.0, "B")
    at["C3"] = (21.6, 224.2, 180.0, "B")
    at["C2"] = (24.2, 225.8, 180.0, "B")
    at["R4"] = (27.6, 222.6, 90.0, "B")
    at["C4"] = (24.0, 219.2, 180.0, "B")
    at["L1"] = (16.8, 222.0, 0.0, "B")
    at["C5"] = (13.2, 218.0, 90.0, "B")
    at["C6"] = (15.8, 217.2, 90.0, "B")
    at["R5"] = (28.0, 225.4, 0.0, "B")
    at["R6"] = (28.0, 227.0, 0.0, "B")
    at["U6"] = (cx - 12.0, 210.0, 90.0, "B")
    at["C7"] = (cx - 12.0, 206.0, 0.0, "B")
    at["C8"] = (cx - 12.0, 214.0, 0.0, "B")
    at["R7"] = (cx + 2.5, 206.0, 0.0, "B")
    at["R8"] = (cx + 2.5, 203.6, 0.0, "B")
    at["C51"] = (34.0, 200.0, 0.0, "B")         # the LED rail's reservoir
    # --- the flipper drivers, by each solenoid's back end, mirrored
    for side, q, rg, rd, d, j, c in (("L", "Q1", "R30", "R31", "D1", "J2", "C61"), ("R", "Q2", "R32", "R33", "D2", "J3", "C62")):
        m = (lambda x: x) if side == "L" else L.mirror_x
        at[q] = (round(m(43.9), 2), 84.0, 0.0, "B")
        at[rg] = (round(m(43.9), 2), 87.4, 0.0, "B")
        at[rd] = (round(m(44.3), 2), 80.6, 0.0, "B")
        at[d] = (round(m(38.5), 2), 86.5, 90.0, "B")
        at[j] = (round(m(28.0), 2), 88.0, 0.0, "B")
        at[c] = (round(m(41.5), 2), 80.5, 90.0, "B")
    at["C60"] = (L.CENTER_X, 100.5, 0.0, "B")     # the bulk capacitor between the drivers
    # --- the holes and fiducials
    for h in holes():
        at[h.ref] = (h.x, h.y, 0.0, "F")
    for ref, x, y in FIDUCIALS_TOP:
        at[ref] = (x, y, 0.0, "F")
    for ref, x, y in FIDUCIALS_BOTTOM:
        at[ref] = (x, y, 0.0, "B")
    # --- the buttons: on top, under the rails and the lockdown bar (each part needs a pocket: README)
    # the rails' buttons: the actuator's axis at y = FLIPPER_BUTTON_Y, the actuator toward the edge, the body under the rail
    at["SW3"] = (1.55, FLIPPER_BUTTON_Y - 2.25, 90.0, "F")
    at["SW4"] = (L.BOARD_W - 1.55, FLIPPER_BUTTON_Y + 2.25, 270.0, "F")
    at["SW5"] = (START_AT[0] - 3.25, START_AT[1] + 2.25, 0.0, "F")
    # --- every LED and its capacitor; every comb
    for led in leds():
        at[led.ref] = (led.x, led.y, led.rot, led.side)
        n = int(led.ref[3:])
        cx_, cy_, crot, cside = led.cap
        at[f"C{100 + n}"] = (cx_, cy_, crot, cside)
    for s in sensors():
        at[s.ref] = (s.anchor[0], s.anchor[1], 0.0, "F")
    # each comb's TVS beside its SENSE land, on the underside, off the flipper brackets and what stands there
    keep = []
    for side, (px, py) in L.PIVOTS.items():
        sgn = 1 if side == "left" else -1
        keep.append(box(px + sgn * 6.0 - 11.5, py + 16.0 - 20.5, px + sgn * 6.0 + 11.5, py + 16.0 + 20.5))
    keep = unary_union(keep)
    taken = [Point(h.x, h.y).buffer(h.d / 2 + 0.6) for h in holes()]
    for s in sensors():
        taken += [Point(s.land_sense).buffer(0.9), Point(s.land_gnd).buffer(0.9)]
    for led in leds():
        hw, hh = (3.9, 2.1) if led.package == "SK6812MINI-E" else (1.5, 1.5)
        if led.side == "B":
            taken.append(box(led.x - hw, led.y - hh, led.x + hw, led.y + hh))
        cx_, cy_, _, cside = led.cap
        if cside == "B":
            taken.append(box(cx_ - 1.0, cy_ - 0.6, cx_ + 1.0, cy_ + 0.6))
    big = {"C60": 5.6, "C51": 5.6}            # the bulk electrolytics' courtyards
    for ref, (x, y, _, side) in at.items():
        if side == "B" and ref[0] in "UJQDLRCY" and not ref.startswith("LED") and not (ref[0] == "C" and len(ref) == 4):
            r = big.get(ref, 3.0)
            taken.append(box(x - r, y - r, x + r, y + r))
    taken = unary_union(taken)
    # the comb's protection, side by side at its land: the TVS on the comb's side, the 1k on to the RP2040
    for i, s in enumerate(sensors()):
        x, y = clear_spot(s.land_sense, taken, keep, size=(3.8, 3.2))
        at[f"D{3 + i}"] = (x, y + 0.8, 0.0, "B")
        at[f"R{50 + i}"] = (x, y - 0.9, 0.0, "B")
        taken = unary_union([taken, box(x - 2.1, y - 1.8, x + 2.1, y + 1.8)])
    return at

if __name__ == "__main__":
    s = sensors()
    print(len(s), "sensors;", len(holes()), "holes;", len(leds()), "LEDs")
    print(sorted(gpio_map().items(), key=lambda kv: kv[1]))
    a = board_art()
    for k, v in a.report.items():
        print(f"{k}: {v}")
