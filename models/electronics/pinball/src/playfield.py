"""The playfield in plan: the furniture's footprints and the board's top-side art, as 2D geometry.

Everything is shapely geometry in the playfield frame (layout.py: mm, y up the field, z = 0 the board's
top). Two consumers read it: the CAD (parts.py and machine.py extrude it) and the board scripts (they write
the same shapes as copper, soldermask openings and silkscreen), so the art on the board and in a render
is one drawing.

The art's layers:
- gold: exposed ENIG (copper with the soldermask opened), each shape on a net. GND is the ornament, the
  pinstripes and the letters; SENSE_* are the sensors' other electrodes. A sensor is an interdigitated
  comb, its fingers 0.4 mm on a 0.8 mm pitch, alternating SENSE and GND: the 8 mm steel ball resting
  across a 0.4 mm gap sags only 5 um, less than the copper's 35 um, so it touches both fingers and closes
  the circuit. Copper of two nets anywhere else stays >= 1.2 mm apart, where the ball's sag (45 um)
  exceeds the copper's height and it cannot bridge them.
- silk: white silkscreen (dot-matrix text, rules, ticks), never on gold.
- inserts: FR-4 windows (no copper, no mask) over the LEDs that light them from below.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from shapely import affinity
from shapely.geometry import LineString, MultiPoint, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

import dotfont
import layout as L

FINGER, PITCH = 0.4, 0.8            # sensor combs
ISOLATE = 1.2                       # copper of two nets elsewhere
PIN = 0.45                          # pinstripes
RES = 16                            # segments per quarter circle in shapely buffers


def circle(x, y, r):
    return Point(x, y).buffer(r, quad_segs=RES)


def ring(x, y, r_in, r_out):
    return circle(x, y, r_out).difference(circle(x, y, r_in))


def stroke(points, width, cap="round"):
    style = {"round": 1, "flat": 2, "square": 3}[cap]
    return LineString(points).buffer(width / 2, quad_segs=RES // 3, cap_style=style, join_style=1)


def rounded_rect(x0, y0, x1, y1, r):
    return box(x0 + r, y0 + r, x1 - r, y1 - r).buffer(r, quad_segs=RES)


# ============================================================================================ footprints
# What stands on the board, in plan: the CAD extrudes these, the art keeps clear of them.

def arch_inner():
    """The playfield's inner outline above ARCH_Y0: the two corner arcs and the straight top, as a polygon
    of the region the ball may roll in up there (x between the rails)."""
    x0, x1 = L.RAIL_W, L.BOARD_W - L.RAIL_W
    r = L.ARCH_R
    top = L.ARCH_TOP
    cy = top - r
    pts = [(x0, L.ARCH_Y0 - 1.0), (x1, L.ARCH_Y0 - 1.0)]
    for k in range(0, 33):
        a = math.radians(90.0 * k / 32)
        pts.append((x1 - r + r * math.cos(a), cy + r * math.sin(a)))
    for k in range(0, 33):
        a = math.radians(90.0 + 90.0 * k / 32)
        pts.append((x0 + r + r * math.cos(a), cy + r * math.sin(a)))
    return Polygon(pts)


def arch_wall():
    inner = arch_inner()
    outer = inner.buffer(L.ARCH_WALL, quad_segs=RES, join_style=1)
    band = outer.difference(inner)
    return band.intersection(box(L.RAIL_W - 0.01, L.ARCH_Y0, L.BOARD_W - L.RAIL_W + 0.01, L.BOARD_L))


def rails():
    y1 = L.BACKBOX_Y
    left = box(0, L.LOCKDOWN_D, L.RAIL_W, y1)
    right = box(L.BOARD_W - L.RAIL_W, L.LOCKDOWN_D, L.BOARD_W, y1)
    return left, right


def lockdown():
    return box(0, 0, L.BOARD_W, L.LOCKDOWN_D)


def shooter_wall():
    return rounded_rect(L.SHOOTER_WALL[0], L.SHOOTER_WALL_Y[0], L.SHOOTER_WALL[1], L.SHOOTER_WALL_Y[1], L.WALL / 2 - 0.01)


def lane_guides():
    """The inlane/outlane guides (left and right), from the apron up to their top posts. Below
    GUIDE_LOW_Y each steps outboard (1.4 mm thick), so the flipper's base and its rubber turn clear of it."""
    out = {}
    y0, yl, yt = L.APRON_Y[1] - 0.5, L.GUIDE_LOW_Y, L.LANE_TOP_Y
    for side, (g0, g1) in (("left", L.GUIDE_L), ("right", L.GUIDE_R)):
        if side == "left":
            pts = [(g0 - 1.4, y0), (g0, y0), (g0, yl), (g1, yl), (g1, yt - 1.0), (g0, yt - 1.0), (g0, yl + 2.0), (g0 - 1.4, yl + 2.0)]
        else:
            pts = [(g1 + 1.4, y0), (g1, y0), (g1, yl), (g0, yl), (g0, yt - 1.0), (g1, yt - 1.0), (g1, yl + 2.0), (g1 + 1.4, yl + 2.0)]
        top = circle((g0 + g1) / 2, yt - 1.0, L.GUIDE / 2)
        out[side] = Polygon(pts).union(top)
    return out


def sling_posts(side: str):
    posts = L.SLING_POSTS
    if side == "right":
        posts = tuple((L.mirror_x(x), y) for x, y in posts)
    return posts


def sling_footprint(side: str):
    """The rubber band's outer line round the three posts."""
    r = L.POST_R + 2 * L.POST_RUBBER
    return unary_union([circle(x, y, r) for x, y in sling_posts(side)]).convex_hull


def sling_active_line(side: str):
    """The active face (top post to bottom-inner post), offset onto the rubber's outer surface."""
    (x0, y0), _, (x2, y2) = sling_posts(side)
    dx, dy = x2 - x0, y2 - y0
    n = math.hypot(dx, dy)
    nx, ny = (-dy / n, dx / n) if side == "left" else (dy / n, -dx / n)   # toward the field's centre
    off = L.POST_R + 2 * L.POST_RUBBER
    return (x0 + nx * off, y0 + ny * off), (x2 + nx * off, y2 + ny * off), (nx, ny)


def top_lane_guides():
    xs = sorted(L.TOP_LANES.values())
    half = L.LANE / 2 + L.GUIDE / 2
    centres = [xs[0] - half] + [(a + b) / 2 for a, b in zip(xs, xs[1:])] + [xs[-1] + half]
    y0, y1 = L.TOP_LANE_Y
    return [rounded_rect(c - L.GUIDE / 2, y0, c + L.GUIDE / 2, y1, L.GUIDE / 2 - 0.01) for c in centres]


def bumper_footprint(name: str):
    x, y = L.BUMPERS[name]
    return circle(x, y, L.BUMPER_R + 0.6)


def target_footprint(name: str):
    y = L.TARGETS[name]
    return box(L.RAIL_W, y - L.TARGET_W / 2 - 0.6, L.TARGET_FACE_X, y + L.TARGET_W / 2 + 0.6)


def apron():
    return box(L.RAIL_W, L.LOCKDOWN_D, L.SHOOTER_WALL[0], L.APRON_Y[1])


def flipper_sweep(side: str):
    """The plan area a bat (with its rubber) sweeps between rest and energised."""
    px, py = L.PIVOTS[side]
    pts = []
    for k in range(0, 23):
        a = L.FLIPPER_REST + (L.FLIPPER_UP - L.FLIPPER_REST) * k / 22
        if side == "right":
            a = 180.0 - a
        pts.append(circle(px + L.FLIPPER_L * math.cos(math.radians(a)),
                          py + L.FLIPPER_L * math.sin(math.radians(a)), L.FLIPPER_RT + L.RUBBER_CS))
    pts.append(circle(px, py, L.FLIPPER_RB + L.RUBBER_CS))
    return unary_union(pts).convex_hull


def field_region():
    """Where the ball rolls on the main field and the shooter lane, inside every wall."""
    inner = box(L.RAIL_W, L.APRON_Y[1], L.BOARD_W - L.RAIL_W, L.ARCH_Y0).union(arch_inner())
    shooter_low = box(L.SHOOTER_LANE[0], L.PLUNGER_REST_Y, L.SHOOTER_LANE[1], L.APRON_Y[1] + 0.01)
    region = inner.union(shooter_low)
    solids = [shooter_wall(), *lane_guides().values(), *top_lane_guides(), sling_footprint("left"),
              sling_footprint("right"), *(bumper_footprint(n) for n in L.BUMPERS),
              *(target_footprint(n) for n in L.TARGETS)]
    return region.difference(unary_union(solids))


# ============================================================================================ the art

@dataclass
class Art:
    gold: list = field(default_factory=list)      # (polygon, net)
    gold_dots: list = field(default_factory=list) # (x, y, diameter, net): round pads
    silk: list = field(default_factory=list)      # polygons
    silk_dots: list = field(default_factory=list) # (x, y, diameter)
    inserts: dict = field(default_factory=dict)   # name -> polygon (the FR-4 window)
    leds: dict = field(default_factory=dict)      # name -> (x, y) of the LED lighting it (under the board)

    def add_gold(self, geom, net="GND"):
        for poly in _polys(geom):
            self.gold.append((poly, net))

    def gold_union(self, net=None):
        return unary_union([p for p, n in self.gold if net is None or n == net])

    def silk_union(self):
        return unary_union(self.silk)


def _polys(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, Polygon):
        return [geom]
    if isinstance(geom, MultiPolygon):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]


# --- the sensors ---------------------------------------------------------------------------------------

def comb(x0, y0, x1, y1, net_a, axis="y", chevron=0.0, spine=0.4):
    """An interdigitated comb in the box (x0, y0)-(x1, y1): fingers across `axis` (axis "y": horizontal
    fingers stacked up y), alternating net_a (the even ones, from the low spine) and GND (from the high
    spine). `chevron` bends each finger into a V by that rise at its middle (an arrow along +axis)."""
    parts = {net_a: [], "GND": []}
    if axis == "y":
        n = int((y1 - y0 - FINGER) / PITCH) + 1
        span = (n - 1) * PITCH
        ys = [y0 + (y1 - y0 - span) / 2 + k * PITCH for k in range(n)]
        lo = box(x0, ys[0] - FINGER / 2, x0 + spine, ys[-1] + FINGER / 2)
        hi = box(x1 - spine, ys[0] - FINGER / 2, x1, ys[-1] + FINGER / 2)
        parts[net_a].append(lo)
        parts["GND"].append(hi)
        for k, y in enumerate(ys):
            mine = net_a if k % 2 == 0 else "GND"
            xa = x0 + (0 if mine == net_a else spine + FINGER)
            xb = x1 - (0 if mine == "GND" else spine + FINGER)
            xm = (x0 + x1) / 2
            pts = [(xa, y), (xm, y + chevron), (xb, y)] if chevron else [(xa, y), (xb, y)]
            parts[mine].append(stroke(pts, FINGER, cap="flat"))
    else:
        n = int((x1 - x0 - FINGER) / PITCH) + 1
        span = (n - 1) * PITCH
        xs = [x0 + (x1 - x0 - span) / 2 + k * PITCH for k in range(n)]
        lo = box(xs[0] - FINGER / 2, y0, xs[-1] + FINGER / 2, y0 + spine)
        hi = box(xs[0] - FINGER / 2, y1 - spine, xs[-1] + FINGER / 2, y1)
        parts[net_a].append(lo)
        parts["GND"].append(hi)
        for k, x in enumerate(xs):
            mine = net_a if k % 2 == 0 else "GND"
            ya = y0 + (0 if mine == net_a else spine + FINGER)
            yb = y1 - (0 if mine == "GND" else spine + FINGER)
            parts[mine].append(stroke([(x, ya), (x, yb)], FINGER, cap="flat"))
    return {k: unary_union(v) for k, v in parts.items()}


def ring_comb(cx, cy, r0, r1, net_a, spine_a=225.0, spine_b=45.0):
    """Concentric rings r0..r1 at the comb's pitch, alternating net_a and GND, each net's rings joined by
    a radial spine and opened where the other net's spine passes (two interleaved combs bent round)."""
    n = int((r1 - r0) / PITCH) + 1
    radii = [r0 + k * PITCH for k in range(n)]
    out = {net_a: [], "GND": []}
    r_lo, r_hi = radii[0] - FINGER / 2, radii[-1] + FINGER / 2

    def spoke(angle):
        a = math.radians(angle)
        return stroke([(cx + r_lo * math.cos(a), cy + r_lo * math.sin(a)),
                       (cx + r_hi * math.cos(a), cy + r_hi * math.sin(a))], FINGER, cap="flat")

    def notch(angle, width):
        a = math.radians(angle)
        return stroke([(cx + (r_lo - 1) * math.cos(a), cy + (r_lo - 1) * math.sin(a)),
                       (cx + (r_hi + 1) * math.cos(a), cy + (r_hi + 1) * math.sin(a))], width, cap="flat")
    for k, r in enumerate(radii):
        mine, other = (net_a, spine_b) if k % 2 == 0 else ("GND", spine_a)
        band = ring(cx, cy, r - FINGER / 2, r + FINGER / 2).difference(notch(other, FINGER + 2 * FINGER))
        out[mine].append(band)
    out[net_a].append(spoke(spine_a))
    out["GND"].append(spoke(spine_b))
    return {k: unary_union(v) for k, v in out.items()}


def sensors():
    """Every sensor comb: name -> {net: geometry}. The nets are SENSE_<name> and GND."""
    s = {}
    # the three top lanes: chevrons pointing up the lane
    y0, y1 = L.TOP_LANE_Y[0] + 2.0, L.TOP_LANE_Y[0] + 13.0
    for name, x in L.TOP_LANES.items():
        s[f"LANE_{name}"] = comb(x - 4.3, y0, x + 4.3, y1, f"SENSE_LANE_{name}", chevron=1.4)
    # the four lower lanes: chevrons pointing down toward the flippers / the drain
    for name, (a, b) in (("OUT_L", L.OUTLANE_L), ("IN_L", L.INLANE_L), ("IN_R", L.INLANE_R), ("OUT_R", L.OUTLANE_R)):
        x = (a + b) / 2
        s[name] = comb(x - 4.3, 66.0, x + 4.3, 76.0, f"SENSE_{name}", chevron=-1.4)
    # the bumpers: rings where the ball's contact point lies when it touches the O-ring
    for name, (x, y) in L.BUMPERS.items():
        s[f"BUMPER_{name}"] = ring_comb(x, y, 8.0, 12.0, f"SENSE_BUMPER_{name}")
    # the targets: bars parallel to each face, where the ball stands when it touches it
    for name, y in L.TARGETS.items():
        f = L.TARGET_FACE_X
        s[f"TARGET_{name}"] = comb(f + 1.6, y - 5.0, f + 6.6, y + 5.0, f"SENSE_TARGET_{name}", axis="x")
    # the slings: a strip along each active face, where the ball stands touching the rubber
    for side in ("left", "right"):
        (ax, ay), (bx, by), (nx, ny) = sling_active_line(side)
        length = math.hypot(bx - ax, by - ay)
        ux, uy = (bx - ax) / length, (by - ay) / length
        local = comb(-length / 2 + 3.5, 2.4, length / 2 - 12.0, 4.8, f"SENSE_SLING_{side[0].upper()}", axis="y")
        mx, my = (ax + bx) / 2, (ay + by) / 2
        s[f"SLING_{side[0].upper()}"] = {net: affinity.affine_transform(g, [ux, nx, uy, ny, mx, my])
                                          for net, g in local.items()}
    # the orbit: down the left wall, where the ball comes round the arch
    s["ORBIT"] = comb(L.FIELD_X0 + 1.4, 140.0, L.FIELD_X0 + 10.6, 150.0, "SENSE_ORBIT", chevron=-1.4)
    # the shooter lane: under the ball resting on the plunger (ball ready)
    x0, x1 = L.SHOOTER_LANE
    s["SHOOTER"] = comb(x0 + 1.0, L.BALL_READY_Y - 3.6, x1 - 1.0, L.BALL_READY_Y + 3.6, "SENSE_SHOOTER")
    # the drain: across the return channel under the apron, right of the flippers' gap
    s["DRAIN"] = comb(L.CENTER_X + 12.0, 14.0, L.CENTER_X + 20.0, 24.0, "SENSE_DRAIN", axis="x")
    return s


# --- the ornament ---------------------------------------------------------------------------------------

def dot_text(text, pitch, at, dot_d, anchor="center", rotate=0.0):
    """Dot-matrix text as dots: [(x, y, diameter)]."""
    return [(x, y, dot_d) for x, y in dotfont.placed(text, pitch, at, anchor, rotate)]


def _keep_dots(dots, *keepouts):
    out = []
    for x, y, d in dots:
        p = Point(x, y)
        if all(not k.intersects(p.buffer(d / 2, quad_segs=4)) for k in keepouts):
            out.append((x, y, d))
    return out


def build_art() -> Art:
    art = Art()
    sens = sensors()
    keep_gnd = []                         # where GND ornament must not come (other nets, inserts, parts)
    for name, nets in sens.items():
        for net, geom in nets.items():
            art.add_gold(geom, net)
            if net != "GND":
                keep_gnd.append(geom.buffer(ISOLATE, quad_segs=8))

    # the inserts: FR-4 windows over the LEDs (each lit from under the board)
    ins = {}
    for i, (x, y) in enumerate(L.BONUS_INSERTS):
        ins[f"BONUS_{i + 1}"] = circle(x, y, L.BONUS_R)
    ins["SHOOT_AGAIN"] = circle(*L.SHOOT_AGAIN, L.INSERT_R + 0.6)
    for k, (x, y) in L.LANE_INSERTS.items():
        ins[f"LANE_{k}"] = circle(x, y, 2.0)
    for k, (x, y) in L.TARGET_INSERTS.items():   # arrows pointing at the targets
        ins[f"TARGET_{k}"] = Polygon([(x - 2.4, y), (x + 1.8, y + 2.6), (x + 1.8, y - 2.6)])
    sx, sy = L.SKILL_INSERT                       # an arrow up the shooter lane
    ins["SKILL"] = Polygon([(sx, sy + 3.2), (sx - 2.6, sy - 1.6), (sx + 2.6, sy - 1.6)])
    for k, (x, y) in L.LANE_LAMPS.items():        # each lane's lamp, flashing when the ball shorts its comb
        ins[f"LAMP_{k}"] = circle(x, y, 1.4)
    ins["LAMP_ORBIT"] = circle(*L.ORBIT_LAMP, 1.4)
    art.inserts = ins
    art.leds = {k: (g.centroid.x, g.centroid.y) for k, g in ins.items()}
    for k, g in ins.items():
        # a gold ring round each window, 0.3 mm clear of the FR-4
        art.add_gold(g.buffer(0.75, quad_segs=RES, join_style=2).difference(g.buffer(0.3, quad_segs=RES, join_style=2)))
        keep_gnd.append(g.buffer(1.0, quad_segs=8, join_style=2))
    keep_gnd = unary_union(keep_gnd)

    # the parts standing on the board: no ornament under them (it would only be hidden)
    parts = unary_union([*rails(), lockdown(), arch_wall(), shooter_wall(), *lane_guides().values(),
                         *top_lane_guides(), sling_footprint("left"), sling_footprint("right"),
                         *(bumper_footprint(n) for n in L.BUMPERS), *(target_footprint(n) for n in L.TARGETS), apron()])
    keep_parts = parts.buffer(0.6, quad_segs=8)

    # gold dots: the letters and the machine's name (GND); white dots: the labels. Each word is a group,
    # and the ornament keeps clear of each group's box.
    label_groups = []

    def word(target, dots_):
        target += dots_
        label_groups.append(dots_)

    gdots = []
    for name, x in L.TOP_LANES.items():
        word(gdots, dot_text(name, 0.8, (x, L.TOP_LANE_Y[0] + 17.2), 0.55))
    for name, y in L.TARGETS.items():
        word(gdots, dot_text(name[0], 0.8, (L.TARGET_FACE_X + 17.0, y), 0.55))
    word(gdots, dot_text("SHORT CIRCUIT", 0.9, ((L.RAIL_W + L.BOARD_W - L.RAIL_W) / 2, L.ARCH_Y0 + 15.5), 0.62))
    art.gold_dots = [(x, y, d, "GND") for x, y, d in _keep_dots(gdots, keep_gnd, keep_parts)]

    sdots = []
    sp, sd = 0.5, 0.34                     # silkscreen dots: 0.34 mm on a 0.5 mm grid (3.4 mm letters)
    for name, (x, y) in L.BUMPERS.items():
        at = {"C1": (x - 11.0, y + 12.6), "C2": (x + 11.0, y + 12.6), "C3": (x + 15.4, y - 2.0)}[name]
        word(sdots, dot_text(name, sp, at, sd))
    word(sdots, dot_text("SKILL SHOT", sp, (L.SHOOTER_X + 2.4, L.SKILL_INSERT[1] - 22.0), sd, rotate=90))
    word(sdots, dot_text("PLUNGE", sp, (L.SHOOTER_X + 2.4, 70.0), sd, rotate=90))
    # the board's title block, as small as a fab's: name, part, revision
    word(sdots, dot_text("SC-PF REV A", 0.36, (L.SHOOTER_X + 2.6, 42.0), 0.26, rotate=90))
    for name, (a_, b_) in (("RETURN", L.INLANE_L), ("RETURN", L.INLANE_R), ("OUT", L.OUTLANE_L), ("OUT", L.OUTLANE_R)):
        word(sdots, dot_text(name, sp, ((a_ + b_) / 2, 49.0), sd, rotate=90))
    word(sdots, dot_text("SPELL GND", 0.42, (L.CENTER_X, L.TOP_LANE_Y[1] + 4.6), 0.3))
    word(sdots, dot_text("VCC", sp, (L.TARGET_FACE_X + 9.4, L.TARGETS["V"] + 7.8), sd))
    word(sdots, dot_text("ORBIT", sp, (L.FIELD_X0 + 13.2, 145.0), sd, rotate=90))
    word(sdots, dot_text("THE BALL IS THE SWITCH", 0.42, (L.SHOOTER_WALL[0] - 4.2, 125.0), 0.3, rotate=90))
    # each sensor's designator, as a schematic names a switch
    for name, ref in L.SWITCHES.items():
        geom = unary_union(list(sens[name].values()))
        minx, miny, maxx, maxy = geom.bounds
        if name.startswith("LANE_"):
            at = ((minx + maxx) / 2, miny - 1.6)
        elif name.startswith("BUMPER_"):
            continue                      # the bumpers carry their C-numbers
        elif name.startswith("TARGET_"):
            # under its arrow and letter: the comb itself fills the gap to the wall
            at = (L.TARGET_FACE_X + 14.2, L.TARGETS[name[7:]] - 4.8)
        elif name in ("OUT_L", "IN_L", "IN_R", "OUT_R"):
            at = ((minx + maxx) / 2, maxy + 1.7)
        elif name.startswith("SLING_"):
            at = ((minx + maxx) / 2 + (-2.4 if name.endswith("L") else 2.4), maxy + 1.4)
        elif name == "ORBIT":
            at = (L.ORBIT_LAMP[0], L.ORBIT_LAMP[1] - 3.4)       # under its lamp
        elif name == "SHOOTER":
            at = ((minx + maxx) / 2, maxy + 1.6)
        else:
            continue
        word(sdots, dot_text(ref, 0.36, at, 0.26))

    # the pinstripe: the field's own outline drawn 2 mm inside its walls
    region = field_region()
    stripe = region.buffer(-2.0, quad_segs=RES, join_style=1)
    lines = stripe.boundary.buffer(PIN / 2, quad_segs=8)
    # the flipper sunburst: rays from the shoot-again insert up between the bats
    sx, sy = L.SHOOT_AGAIN
    rays = []
    for k in range(-5, 6):
        a = math.radians(90.0 + k * 9.0)
        r0, r1 = L.INSERT_R + 2.2, 14.0 - abs(k) * 0.7
        rays.append(stroke([(sx + r0 * math.cos(a), sy + r0 * math.sin(a)),
                            (sx + r1 * math.cos(a), sy + r1 * math.sin(a))], 0.35))
    # the shooter lane's ruler: a tick every 5 mm, a long one every 10
    ticks = []
    for k, y in enumerate(range(30, 150, 5)):
        long_ = k % 2 == 0
        x0 = L.SHOOTER_LANE[0] + 0.9
        ticks.append(stroke([(x0, y), (x0 + (2.6 if long_ else 1.4), y)], 0.3, cap="flat"))
    # the bonus ladder's rail: a gold spine between the five inserts, flanked by vias
    bx = L.CENTER_X
    ladder = [stroke([(bx, L.BONUS_INSERTS[i][1] + L.BONUS_R + 1.6), (bx, L.BONUS_INSERTS[i + 1][1] - L.BONUS_R - 1.6)], 0.5)
              for i in range(len(L.BONUS_INSERTS) - 1)]
    vias = [ring(x + dx, y, 0.2, 0.45) for (x, y) in L.BONUS_INSERTS for dx in (-4.4, 4.4)]
    # stitching vias along the outer pinstripe, every 6 mm: ground's own texture
    edge = region.buffer(-2.0, quad_segs=RES, join_style=1).boundary
    for k in range(int(edge.length / 6.0)):
        p = edge.interpolate(k * 6.0 + 3.0)
        vias.append(ring(p.x, p.y, 0.18, 0.42))
    fids = [circle(x, y, 0.5) for x, y in L.FIDUCIALS]
    # the radiance: fine rays fanning down the field from behind the top lanes, an Art Deco sunrise the
    # rest of the ornament sits in (clipped clear of every sensor, window and part)
    fan = []
    fx, fy = L.CENTER_X, L.ARCH_TOP + 26.0
    for k in range(-26, 27):
        a = math.radians(270.0 + k * 2.6)
        r0 = 62.0 + (0.0 if k % 2 == 0 else 14.0)
        r1 = 250.0
        fan.append(stroke([(fx + r0 * math.cos(a), fy + r0 * math.sin(a)),
                           (fx + r1 * math.cos(a), fy + r1 * math.sin(a))], 0.26, cap="round"))
    main_field = region.intersection(box(0, 0, L.SHOOTER_WALL[0], L.BOARD_L))
    fan = unary_union(fan).intersection(main_field.buffer(-3.2, quad_segs=8)).difference(
        unary_union([circle(x, y, 13.4) for x, y in L.BUMPERS.values()]))
    # a second, finer pinstripe inside the first
    lines2 = region.buffer(-3.1, quad_segs=RES, join_style=1).boundary.buffer(0.14, quad_segs=6)
    ornament = unary_union([lines, lines2, fan, *rays, *ticks, *ladder, *vias])
    fid_clear = unary_union([circle(x, y, 1.6) for x, y in L.FIDUCIALS])
    # the labels keep their ground: a box round each word, the ornament stopped 0.6 mm short of it
    keep_labels = unary_union([MultiPoint([(x, y) for x, y, *_ in group]).envelope.buffer(0.9, join_style=2)
                               for group in label_groups if group])
    ornament = ornament.difference(keep_gnd).difference(keep_parts).difference(keep_labels).difference(fid_clear)
    art.add_gold(ornament, "GND")
    art.add_gold(unary_union(fids), "GND")

    gold_all = unary_union([p for p, _ in art.gold] + [circle(x, y, d / 2) for x, y, d, _ in art.gold_dots]).buffer(0.3, quad_segs=8)
    win = unary_union(list(ins.values())).buffer(0.6, quad_segs=8)
    art.silk_dots = _keep_dots(sdots, gold_all, win, keep_parts)
    return art


def gold_by_net(art: Art):
    out = {}
    for poly, net in art.gold:
        out.setdefault(net, []).append(poly)
    return {k: unary_union(v) for k, v in out.items()}


if __name__ == "__main__":
    a = build_art()
    nets = gold_by_net(a)
    print({k: round(v.area, 1) for k, v in nets.items()})
    print("inserts", len(a.inserts), "gold dots", len(a.gold_dots), "silk dots", len(a.silk_dots))
