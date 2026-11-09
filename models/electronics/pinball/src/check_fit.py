"""Does SHORT CIRCUIT fit, and does it play? Run: cad run src/check_fit.py   (exits 1 on any failure)

1. Interference: the overlap volume of every pair of parts whose boxes meet, the whole machine in the world
   (the table, the cabinet, the legs), the flippers at rest. Contact is fine; any overlap fails unless the pair
   is in PRESSED (parts meant to be pressed together, each with its reason). Coatings (copper, silkscreen, the
   bare FR-4 windows, plating: microns on a surface) are not parts here.
2. The ball's room: every part on the playfield sliced at nine heights through the ball (playfield frame, z up
   from the board's top); each slice grown by the ball's own radius at that height is where the ball's centre
   cannot be. What is left is where it can roll. Every lane's narrowest width is measured across it, and one
   connected region must take the ball from the plunger round the arch, through each top lane, the orbit and
   the bumpers, down each inlane and outlane and between the flippers to the drain.
3. The flippers: each bat swept from rest to energised in 5 degree steps against every other part.
4. The poses the pictures use: the ball at each of them against every part.
5. Heights: the glass over the tallest part under it; the sling plastics over the ball.
"""
from __future__ import annotations

import math
import sys
import time

import build123d as bd
from cad.build123d import overlap_volume
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

import layout as L
import machine as M
import parts as X

T0 = time.time()
R = L.BALL_R
FAILS: list[str] = []
EPS = 1e-3                     # mm^3: overlaps below this are the kernel's noise, not geometry

# the coatings: a few microns of metal or ink on a surface, or the board's own bare FR-4 showing through
COATING = ("gold_", "silkscreen", "insert_", "edge_plating", "backglass_gold", "backglass_silk", "backglass_edge",
           "apron_card_1_gold", "apron_card_2_gold", "sling_left_gold", "sling_right_gold", "sling_left_dots",
           "sling_right_dots", "sling_left_edge", "sling_right_edge", "flipper_left_edge", "flipper_right_edge",
           "flipper_left_ring", "flipper_right_ring")
# parts meant to be pressed together, and why
PRESSED = {
    ("left_solenoid_plunger", "left_link"): "pinned through the plunger's cross hole (stand-in)",
    ("right_solenoid_plunger", "right_link"): "pinned through the plunger's cross hole (stand-in)",
    ("left_crank", "left_return_spring"): "the return spring's hook round the crank",
    ("right_crank", "right_return_spring"): "the return spring's hook round the crank",
}


def coating(label: str) -> bool:
    return label.startswith(COATING)


def fail(msg: str) -> None:
    FAILS.append(msg)
    print("  FAIL", msg)


def boxes_meet(a, b, pad=0.01) -> bool:
    A, B = a.bounding_box(), b.bounding_box()
    return not (A.max.X < B.min.X - pad or B.max.X < A.min.X - pad or A.max.Y < B.min.Y - pad or
                B.max.Y < A.min.Y - pad or A.max.Z < B.min.Z - pad or B.max.Z < A.min.Z - pad)


def pressed(a: str, b: str) -> bool:
    return (a, b) in PRESSED or (b, a) in PRESSED or any(
        a.startswith(x) and b.startswith(y) or a.startswith(y) and b.startswith(x) for x, y in PRESSED)


def overlaps(group_a, group_b, same=False):
    """[(label a, label b, volume)] of pairs that overlap and are not pressed."""
    out = []
    for i, a in enumerate(group_a):
        for j, b in enumerate(group_b):
            if same and j <= i:
                continue
            if a is b or not boxes_meet(a, b):
                continue
            v = overlap_volume(a, b)
            if v > EPS and not pressed(a.label, b.label):
                out.append((a.label, b.label, round(v, 4)))
    return out


# ----------------------------------------------------------------------------------------------- 1. interference
print("1. interference (the machine at rest, in the world)")
table = [p for p in M.table(False, None, None, None, True) if not coating(p.label)]
T = M.table_to_world()
world = []
for p in table:
    q = T * p
    q.label = p.label
    world.append(q)
frame = M.cabinet(T) + M.legs(T)
everything = world + frame
bad = overlaps(everything, everything, same=True)
print(f"  {len(everything)} parts; overlaps: {bad if bad else 'none'}")
for a, b, v in bad:
    fail(f"{a} overlaps {b} by {v} mm^3")

# ----------------------------------------------------------------------------------------------- 2. the ball's room
print("2. the ball's room (playfield frame, sliced through the ball)")
HEIGHTS = (0.25, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 7.75)
STANDING = [p for p in table if p.label not in ("playfield_pcb", "glass") and p.bounding_box().min.Z < 2 * R
            and p.bounding_box().max.Z > 0.0 and p.bounding_box().min.Y < L.BOARD_L]


def slice_at(part, h):
    """The part's plan section at height h above the board's top, as shapely geometry."""
    bb = part.bounding_box()
    if not (bb.min.Z < h < bb.max.Z):
        return None
    cut = part & bd.Pos((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, h) * bd.Box(
        bb.size.X + 2, bb.size.Y + 2, 0.002)
    tris = []
    for f in cut.faces():
        if f.normal_at().Z < 0.99:
            continue
        verts, idx = f.tessellate(0.02, 10.0)
        tris += [Polygon([(verts[i].X, verts[i].Y) for i in t]) for t in idx]
    return unary_union([t for t in tris if t.area > 0]) if tris else None


forbidden = []
for h in HEIGHTS:
    r = math.sqrt(max(R * R - (h - R) ** 2, 0.0))
    for p in STANDING:
        s = slice_at(p, h)
        if s is not None and not s.is_empty:
            forbidden.append(s.buffer(r, quad_segs=16))
forbidden = unary_union(forbidden)
# the board's own edge: the ball's centre stays a radius inside it (the rails stand there anyway)
board = box(0, 0, L.BOARD_W, L.BOARD_L)
free = board.buffer(-R).difference(forbidden)

PLACES = {
    "plunger (ball ready)": (L.SHOOTER_X, L.BALL_READY_Y),
    "shooter lane, top": (L.SHOOTER_X, L.SHOOTER_WALL_Y[1] - 4.0),
    "the arch": (L.CENTER_X, L.ARCH_TOP - 8.0),
    **{f"top lane {k}": (x, sum(L.TOP_LANE_Y) / 2) for k, x in L.TOP_LANES.items()},
    "orbit": (L.FIELD_X0 + 6.0, 145.0),
    "between the bumpers": (L.CENTER_X, 122.0),
    **{f"{n}": ((a + b) / 2, (L.LANE_BOTTOM_Y + L.LANE_TOP_Y) / 2) for n, (a, b) in
       (("left outlane", L.OUTLANE_L), ("left inlane", L.INLANE_L), ("right inlane", L.INLANE_R),
        ("right outlane", L.OUTLANE_R))},
    "above the flippers": (L.CENTER_X, 64.0),
    "between the flippers": (L.CENTER_X, L.FLIPPER_Y - 4.0),
    "the drain, under the apron": (L.CENTER_X, (L.APRON_Y[0] + L.APRON_Y[1]) / 2),
}
parts_of_free = list(free.geoms) if free.geom_type == "MultiPolygon" else [free]
start = Point(PLACES["plunger (ball ready)"])
region = min(parts_of_free, key=lambda g: g.distance(start))
if region.distance(start) > 0.05:
    fail(f"the ball's ready place is {region.distance(start):.2f} mm from where its centre may be")
for name, (x, y) in PLACES.items():
    d = region.distance(Point(x, y))
    ok = d < 0.05
    print(f"  {'ok  ' if ok else 'FAIL'} {name} ({x:.1f}, {y:.1f}){'' if ok else f': {d:.2f} mm out of reach'}")
    if not ok:
        fail(f"the ball cannot reach {name}")


def lane_width(x0, x1, y):
    """The widest ball the free space lets through across the lane at height y: the centre's span + 2R."""
    seg = LineString([(x0 - 6, y), (x1 + 6, y)]).intersection(region)
    if seg.is_empty:
        return 0.0
    pieces = [g for g in getattr(seg, "geoms", [seg]) if g.length > 0]
    mid = Point((x0 + x1) / 2, y)
    best = min(pieces, key=lambda g: g.distance(mid)) if pieces else None
    return (best.length + 2 * R) if best is not None else 2 * R


def narrowest(x0, x1, ys):
    return min((lane_width(x0, x1, y), y) for y in ys)


LANES = {
    "shooter lane": (*L.SHOOTER_LANE, [y / 2 for y in range(int(2 * (L.BALL_READY_Y + 6)), int(2 * L.SHOOTER_WALL_Y[1]))]),
    **{f"top lane {k}": (x - L.LANE / 2, x + L.LANE / 2, [y / 2 for y in range(int(2 * L.TOP_LANE_Y[0]) + 1, int(2 * L.TOP_LANE_Y[1]))])
       for k, x in L.TOP_LANES.items()},
    **{n: (a, b, [y / 2 for y in range(int(2 * L.LANE_BOTTOM_Y) + 2, int(2 * L.LANE_TOP_Y) - 2)]) for n, (a, b) in
       (("left outlane", L.OUTLANE_L), ("left inlane", L.INLANE_L), ("right inlane", L.INLANE_R),
        ("right outlane", L.OUTLANE_R))},
}
print(f"  lanes (the widest ball each lets through at its narrowest; the ball is {L.BALL_D:.1f} mm):")
for name, (x0, x1, ys) in LANES.items():
    w, y = narrowest(x0, x1, ys)
    ok = w >= L.BALL_D + 0.5
    print(f"    {'ok  ' if ok else 'FAIL'} {name}: {w:.2f} mm at y {y:.1f} ({w - L.BALL_D:+.2f} mm)")
    if not ok:
        fail(f"{name} lets through {w:.2f} mm at y {y:.1f}, less than the ball and 0.5 mm")
# each outlane must lead the ball down under the apron to the drain without leaving the lane
for name, (x0, x1) in (("left outlane", L.OUTLANE_L), ("right outlane", L.OUTLANE_R)):
    strip = region.intersection(box(x0 - 1.5, 0.0, x1 + 1.5, L.LANE_TOP_Y))
    pieces = list(getattr(strip, "geoms", [strip]))
    mid = Point((x0 + x1) / 2, (L.LANE_BOTTOM_Y + L.LANE_TOP_Y) / 2)
    lane = min(pieces, key=lambda g: g.distance(mid)) if pieces else None
    ok = lane is not None and lane.bounds[1] < L.APRON_Y[1] - 4.0
    print(f"  {'ok  ' if ok else 'FAIL'} {name} drains under the apron"
          f"{'' if ok else f' (the lane stops at y {lane.bounds[1]:.1f})' if lane is not None else ''}")
    if not ok:
        fail(f"the {name} does not drain")
# the gap between the flippers at rest: the ball must drain down the middle
gap = lane_width(L.flipper_tip("left")[0], L.flipper_tip("right")[0], L.flipper_tip("left")[1])
print(f"  between the flipper tips at rest: {gap:.2f} mm ({gap - L.BALL_D:+.2f} mm)")
if gap < L.BALL_D + 0.5:
    fail(f"the ball cannot drain between the flippers ({gap:.2f} mm)")

# ----------------------------------------------------------------------------------------------- 3. the flippers' sweep
print("3. the flippers swept from rest to energised")
others = [p for p in table if not p.label.startswith(("flipper_left", "flipper_right"))]
for side in ("left", "right"):
    worst = []
    for k in range(0, 12):
        a = min(L.FLIPPER_REST + 5.0 * k, L.FLIPPER_UP)
        bat = [p for p in X.flipper(side, a) if not coating(p.label)]
        worst += [(f"{side} flipper at {a:+.0f} deg", *rest) for rest in overlaps(bat, others)]
        if a >= L.FLIPPER_UP:
            break
    print(f"  {side}: {'free' if not worst else worst}")
    for w in worst:
        fail(f"{w[0]}: {w[1]} meets {w[2]} ({w[3]} mm^3)")

# ----------------------------------------------------------------------------------------------- 4. the pictures' poses
print("4. the ball in the pictures' poses")
POSES = {"ready on the plunger": (L.SHOOTER_X, L.BALL_READY_Y),
         "lit (on the bonus ladder)": (L.CENTER_X, 78.0),
         "on the N lane's comb": (L.TOP_LANES["N"], L.TOP_LANE_Y[0] + 7.6),
         "against bumper C3": M._bumper_touch(),
         "cradled on the left flipper": (26.98, 53.46)}
for name, (x, y) in POSES.items():
    flippers_up = name.startswith("cradled")
    ball = X.ball(x, y)
    pose_parts = others + [p for p in X.flipper("left", L.FLIPPER_UP if flippers_up else None)
                           + X.flipper("right", None) if not coating(p.label)]
    hit = overlaps([ball], [p for p in pose_parts if p.label != "ball"])
    print(f"  {'ok  ' if not hit else 'FAIL'} {name} ({x:.2f}, {y:.2f}){'' if not hit else f': {hit}'}")
    for h in hit:
        fail(f"the ball {name} meets {h[1]} ({h[2]} mm^3)")

# ----------------------------------------------------------------------------------------------- 5. heights
print("5. heights")
under_glass = [p for p in table if p.label not in ("glass", "playfield_pcb") and not p.label.startswith(
    ("rail_", "lockdown", "plunger", "start_", "flipper_button", "backbox", "backglass", "dmd", "apron"))
    and p.bounding_box().min.Z >= -0.01 and p.bounding_box().max.Y < L.BACKBOX_Y]
tallest = max(under_glass, key=lambda p: p.bounding_box().max.Z)
glass = next(p for p in M.table(False, None, None, None, True) if p.label == "glass")
gz = glass.bounding_box().min.Z
clear = gz - tallest.bounding_box().max.Z
print(f"  glass underside z {gz:.2f}; tallest part under it: {tallest.label} at {tallest.bounding_box().max.Z:.2f} "
      f"({clear:+.2f} mm)")
if clear < 0.3:
    fail(f"the glass clears {tallest.label} by {clear:.2f} mm")
for side in ("left", "right"):
    plastic = next(p for p in table if p.label == f"sling_{side}_board")
    z = plastic.bounding_box().min.Z
    print(f"  {side} sling plastic underside z {z:.2f}: {z - L.BALL_D:+.2f} mm over the ball")
    if z - L.BALL_D < 0.3:
        fail(f"the {side} sling plastic clears the ball by {z - L.BALL_D:.2f} mm")

print(f"{'FAILED' if FAILS else 'PASSED'}: {len(FAILS)} failure(s) in {time.time() - T0:.0f} s")
if FAILS:
    sys.exit(1)
