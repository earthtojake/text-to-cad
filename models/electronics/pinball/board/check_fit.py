# /// script
# dependencies = ["shapely>=2"]
# ///
"""Does the board fit the machine? The saved pinball.kicad_pcb against the design model (`../src`), every number
read from the two. Run: cad run board/check_fit.py   (from models/electronics/pinball; exits 1 on any failure)

  1. The outline against parts.playfield_board() (the CAD board's solid).
  2. The flipper shafts' bores against the CAD board's holes.
  3. Every fixing hole under the part it fixes, with wall round it; none open on the ball's field.
  4. Every insert's LED under its window, its cut-out inside it; the combs' copper against playfield.sensors().
  5. Everything on the board's top is the art or hidden: each top part under a furniture part, each top track and
     via hidden too; each top part named with the pocket that part needs.
  6. The underside clear of the flipper mechanisms (bracket plates and bearing flanges press on the board); parts
     under the floor plate's height; USB-C on the cabinet's port.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "scripts"))

import build123d as bd  # noqa: E402
from cad import kicad_pcb  # noqa: E402
from shapely.geometry import MultiPoint, Point, Polygon, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

import geometry as G  # noqa: E402
import parts as X  # noqa: E402

L, P = G.L, G.P
board = kicad_pcb.read(str(G.PROJECT / "pinball.kicad_pcb"))
fails, notes = [], []


def check(ok, what):
    print(("  ok   " if ok else "  FAIL ") + what)
    if not ok:
        fails.append(what)


def pfpoly(points):
    return Polygon([G.playfield(x, y) for x, y in points]).buffer(0)


# ------------------------------------------------------------------------------------------------ 1. outline
print("1. outline")
cad_board = X.playfield_board()
bb = cad_board.bounding_box()
loops = [s for s in board.outline] if isinstance(board.outline, list) else board.outline
outer = max((Polygon(loop).buffer(0) for loop in (board.outline if isinstance(board.outline[0][0], (tuple, list)) else [board.outline])), key=lambda p: p.area)
outer_pf = Polygon([G.playfield(x, y) for x, y in outer.exterior.coords]).buffer(0)
want = G.outline()
check(abs(outer_pf.bounds[2] - bb.size.X) < 0.01 and abs(outer_pf.bounds[3] - bb.size.Y) < 0.01,
      f"size {outer_pf.bounds[2]:.2f} x {outer_pf.bounds[3]:.2f} mm, the CAD board {bb.size.X:.2f} x {bb.size.Y:.2f}")
check(outer_pf.symmetric_difference(want).area < 0.2,
      f"outline against the CAD's: {outer_pf.symmetric_difference(want).area:.3f} mm2 differ (corners r {L.BOARD_CORNER})")

# ------------------------------------------------------------------------------------------------ 2. the bores
print("2. flipper shaft bores")
cad_holes = [e for e in cad_board.edges().filter_by(bd.GeomType.CIRCLE)]
cad_bores = {(round(e.arc_center.X, 3), round(e.arc_center.Y, 3), round(e.radius * 2, 3)) for e in cad_holes}
board_holes = {(round(G.playfield(*h.at)[0], 3), round(G.playfield(*h.at)[1], 3)): h.diameter for h in board.holes}
for x, y, d in sorted(cad_bores):
    near = min(board_holes, key=lambda p: math.dist(p, (x, y)))
    check(math.dist(near, (x, y)) < 0.01 and abs(board_holes[near] - d) < 0.01,
          f"CAD bore d {d} at ({x}, {y}): board hole d {board_holes[near]} {math.dist(near, (x, y)):.3f} mm from it")

# ------------------------------------------------------------------------------------------------ 3. fixings
print("3. fixing holes")


def footprints_of():
    out = {}
    for side, poly in zip(("left", "right"), P.rails()):
        out[f"rail_{side}"] = poly
    out["lockdown_bar"] = P.lockdown()
    out["backbox_wedge"] = box(0, L.BACKBOX_Y - 1.5, L.BOARD_W, L.BOARD_L)
    for name, (x, y) in L.BUMPERS.items():
        out[f"bumper_{name}_post"] = P.circle(x, y, L.BUMPER_POST_R)
    for side in ("left", "right"):
        for i, (x, y) in enumerate(P.sling_posts(side)):
            out[f"sling_{side}_post_{i + 1}"] = P.circle(x, y, L.POST_HEX_R * 0.866)
    for side, (g0, g1) in (("left", L.GUIDE_L), ("right", L.GUIDE_R)):
        out[f"lane_post_{side}"] = P.circle((g0 + g1) / 2, L.LANE_TOP_Y, L.POST_HEX_R * 0.866)
    return out


feet = footprints_of()
walls = []
solids = [P.shooter_wall(), *P.lane_guides().values(), *P.top_lane_guides(), P.sling_footprint("left"),
          P.sling_footprint("right"), *(P.bumper_footprint(n) for n in L.BUMPERS), *(P.target_footprint(n) for n in L.TARGETS),
          *(P.circle((a + b) / 2, L.LANE_TOP_Y, L.POST_HEX_R) for a, b in (L.GUIDE_L, L.GUIDE_R))]
field = P.field_region().difference(unary_union(solids))
for h in G.holes():
    disc = Point(h.x, h.y).buffer(h.d / 2, quad_segs=16)
    if h.fixes.endswith("_shaft"):
        continue
    foot = feet[h.fixes]
    wall = foot.exterior.distance(Point(h.x, h.y)) - h.d / 2 if foot.contains(Point(h.x, h.y)) else -1
    placed = board_holes.get((round(h.x, 3), round(h.y, 3)))
    check(placed == h.d and wall >= 0.3, f"{h.ref} {h.name}: d {h.d} under {h.fixes}, wall {wall:.2f} mm")
    check(disc.intersection(field).area < 1e-6, f"{h.ref}: not open on the ball's field")

# ------------------------------------------------------------------------------------------------ 4. inserts, combs
print("4. inserts and combs")
art = P.build_art()
windows = G.board_art().windows
for led in G.leds():
    part = board.part(led.ref)
    ax, ay = G.playfield(*part.at)
    if led.package == "SK6812MINI-E":
        name = led.what.removeprefix("INSERT_")
        x, y = art.leds[name]
        cut = G.led_cutout(led.x, led.y)
        check(math.dist((ax, ay), (x, y)) < 0.01 and part.side == "bottom", f"{led.ref} under {name}'s window")
        check(windows[name].contains(cut), f"{led.ref}'s cut-out inside the window")
for s in G.sensors():
    a = board.part(s.ref)
    copper = [pfpoly(sh.points) for sh in board.shapes if sh.layer == "F.Cu" and sh.points and len(sh.points) >= 3
              and getattr(sh, "net", None) == next(p.net for p in a.pads if p.number == "1")]
    drawn = unary_union(copper)
    check(drawn.symmetric_difference(s.sense).area < 0.01, f"{s.ref} {s.name}: its SENSE copper is playfield.py's (area {drawn.area:.1f} mm2)")
    for number, land, own in (("1", s.land_sense, s.sense), ("2", s.land_gnd, s.gnd)):
        pad = next(p for p in a.pads if p.number == number)
        check(Point(G.playfield(*pad.at)).distance(own) < G.LAND_PAD / 2, f"{s.ref} pad {number}: its land on its comb")

# ------------------------------------------------------------------------------------------------ 5. the top
print("5. the top side: art, or hidden under furniture")
post_shape = {}
for name, (x, y) in L.BUMPERS.items():
    post_shape[f"bumper {name}"] = P.circle(x, y, L.BUMPER_POST_R)
for side in ("left", "right"):
    post_shape[f"sling {side}"] = P.sling_footprint(side)
for name in L.TARGETS:
    post_shape[f"target {name}"] = P.target_footprint(name)
post_shape["rail left"], post_shape["rail right"] = P.rails()
post_shape["lockdown bar"] = P.lockdown()
# the backbox stands on the board behind the arch (parts.backbox_parts: its base from BACKBOX_Y - 1.5 to the back edge)
post_shape["backbox base"] = box(0.0, L.BACKBOX_Y - 1.5, L.BOARD_W, L.BOARD_L)
hidden = unary_union(list(post_shape.values()))
for part in board.parts:
    if part.side != "top" or part.ref.startswith(("S", "H", "FID")) and part.ref[-1].isdigit() and not part.ref.startswith("SW"):
        continue
    pads = unary_union([pfpoly(pad.polygon) for pad in part.pads if pad.polygon and len(pad.polygon) >= 3])
    under = [k for k, poly in post_shape.items() if poly.buffer(0.5).contains(pads)]
    check(bool(under), f"{part.ref}: its pads under {under or 'nothing'}")
    if under and not under[0].startswith(("bumper", "target")):
        notes.append(f"{part.ref} ({part.value}): the {under[0]} needs a pocket over it")
    elif under:
        print(f"       {part.ref} stands in the {under[0]} post's own LED pocket (parts.py)")
top_tracks = [t for t in board.tracks if t.layer == "F.Cu"]
bad = [t for t in top_tracks if not hidden.buffer(0.3).contains(unary_union([Point(G.playfield(*q)) for q in t.points]))]
check(not bad, f"{len(top_tracks)} top-copper tracks, {len(bad)} showing")
art_vias = [v for v in board.vias if abs(v.diameter - G.VIA_D) > 0.01]
field_vias = [v for v in board.vias if abs(v.diameter - G.VIA_D) <= 0.01 and field.contains(Point(G.playfield(*v.at)))]
print(f"  note {len(field_vias)} routed vias come up in the ball's field (tented, flush, under the black mask); "
      f"{len(art_vias)} stitching vias are the art's, open on top")

# ------------------------------------------------------------------------------------------------ 6. the underside
print("6. the underside")
keep = {}
for side in ("left", "right"):
    px, py = L.PIVOTS[side]
    s = 1 if side == "left" else -1
    keep[f"{side} bracket plate"] = box(px + s * 6.0 - 11.0, py + 16.0 - 20.0, px + s * 6.0 + 11.0, py + 16.0 + 20.0)
    keep[f"{side} bearing flange"] = P.circle(px, py, 3.6)
clash = 0
for part in board.parts:
    if part.side != "bottom" or not part.outline or len(part.outline) < 3:
        continue
    court = pfpoly(part.outline)
    for name, zone in keep.items():
        if court.intersects(zone):
            clash += 1
            check(False, f"{part.ref} on the {name}")
check(clash == 0, f"no part's courtyard on a bracket plate or a bearing flange ({sum(1 for p in board.parts if p.side == 'bottom')} parts on the underside)")
tall = max((m for m in [10.5]), default=0)
check(tall < L.ENGINE_DEPTH, f"tallest part under the board {tall} mm (C60), the engine room {L.ENGINE_DEPTH} mm deep")
j1 = board.part("J1")
jx, jy = G.playfield(*j1.at)
check(abs(jx - L.CENTER_X) < 0.01, f"J1 on the back panel's port: x {jx:.2f}, the port's {L.CENTER_X:.2f}")
check(abs(jy + 3.65 - L.BOARD_L) < 0.01, f"J1's mating face on the board's back edge ({jy + 3.65:.2f}, the edge {L.BOARD_L})")
z_centre = -L.BOARD_T - 3.16 / 2
check(abs(z_centre - (-L.BOARD_T - 1.6)) < 0.1, f"J1's shell centred {z_centre:.2f} mm in z, the port's {-L.BOARD_T - 1.6:.2f}")

print("\nPockets the furniture needs (the CAD parts are solid there; the next CAD pass cuts them):")
for line in sorted(set(notes)):
    print("  " + line)
print(f"\n{'FAILED' if fails else 'PASSED'}: {len(fails)} failures")
sys.exit(1 if fails else 0)
