"""SHORT CIRCUIT's parts, each built in the playfield frame (layout.py: the board's top face at z = 0).

The board's art comes from playfield.py; the parts that stand on it read their places from layout.py. Units mm.
"""
from __future__ import annotations

import math

import build123d as bd

import layout as L
import looks
import playfield as P

Z = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)


# ============================================================================================ helpers

def tag(shape, label, material, color=None):
    shape.label = label
    shape.material = material
    if color is not None:
        shape.color = color
    return shape


def faces(geom, z=0.0):
    """shapely (Multi)Polygon -> build123d faces on the plane z."""
    out = []
    for poly in P._polys(geom):
        outer = bd.Wire.make_polygon([bd.Vector(x, y, z) for x, y in poly.exterior.coords[:-1]], close=True)
        inner = [bd.Wire.make_polygon([bd.Vector(x, y, z) for x, y in r.coords[:-1]], close=True)
                 for r in poly.interiors]
        out.append(bd.Face(outer, inner))
    return out


def slab(geom, z0, z1):
    """shapely geometry extruded from z0 to z1, as one Compound of solids."""
    solids = [bd.Solid.extrude(f, bd.Vector(0, 0, z1 - z0)) for f in faces(geom, z0)]
    return solids[0] if len(solids) == 1 else bd.Compound(solids)


def cyl(x, y, z0, z1, r):
    return bd.Pos(x, y, z0) * bd.Cylinder(r, z1 - z0, align=Z)


def dots(points, z0, h):
    """Round dots (x, y, d) as short cylinders standing on z0."""
    return bd.Compound([bd.Solid.make_cylinder(d / 2, h, bd.Plane((x, y, z0))) for x, y, d, *_ in points])


def hexagon(x, y, z0, z1, across_flats, angle=0.0):
    return bd.Pos(x, y, z0) * bd.Rot(0, 0, angle) * bd.extrude(bd.RegularPolygon(across_flats / math.sqrt(3), 6), z1 - z0)


def fillet_top(solid, r):
    try:
        return bd.fillet(solid.edges().group_by(bd.Axis.Z)[-1], r)
    except Exception:
        return solid


# ============================================================================================ the board

def board_outline():
    return P.rounded_rect(0, 0, L.BOARD_W, L.BOARD_L, L.BOARD_CORNER)


def playfield_board():
    """The 4-layer playfield board: black soldermask, its edge plated in gold, the bearing holes."""
    body = slab(board_outline(), -L.BOARD_T, 0.0)
    holes = [cyl(x, y, -L.BOARD_T - 1, 1, 3.0) for x, y in L.PIVOTS.values()]
    body = body - bd.Compound(holes)
    return tag(body, "playfield_pcb", looks.soldermask())


def edge_plating():
    o = board_outline()
    band = o.buffer(0.05, quad_segs=16, join_style=1).difference(o)
    return tag(slab(band, -L.BOARD_T, 0.0), "edge_plating", looks.enig())


def art_parts(art, lit: bool = False):
    """The board's top-side art as parts: each sensor's gold, the ornament, the dots, the silkscreen, the
    inserts (lit or not)."""
    out = []
    by_net = P.gold_by_net(art)
    for net, geom in sorted(by_net.items()):
        name = "gold_ornament" if net == "GND" else "gold_" + net.lower().replace("sense_", "sensor_")
        out.append(tag(slab(geom, 0.0, 0.035), name, looks.enig()))
    out.append(tag(dots(art.gold_dots, 0.0, 0.035), "gold_letters", looks.enig()))
    out.append(tag(dots([(x, y, d) for x, y, d in art.silk_dots], 0.0, 0.02), "silkscreen", looks.silkscreen()))
    for name, geom in art.inserts.items():
        out.append(tag(slab(geom, 0.0, 0.03), f"insert_{name.lower()}", looks.fr4_window(lit)))
    return out


# ============================================================================================ the frame

def rail(side: str):
    """A side rail on the board's edge strip, Braun-tight: 6 mm wide; its inner half 11.2 mm tall, where the
    glass rests; its outer half rising to the glass's top (13.2) as a lip that locates it, chamfered 1 mm;
    the flipper button's bezel in its face. MJF PA12, dyed black."""
    w, y0, y1 = L.RAIL_W, L.LOCKDOWN_D, L.BACKBOX_Y - 2.0
    top = L.GLASS_Z + L.GLASS_T
    prof = bd.Polygon((0, 0), (w, 0), (w, L.GLASS_Z), (w / 2, L.GLASS_Z), (w / 2, top), (0, top), align=None)
    body = bd.Pos(0, y0, 0) * bd.extrude(bd.Plane.XZ * prof, amount=-(y1 - y0))
    outer_top = body.edges().filter_by(bd.Axis.Y).group_by(bd.Axis.Z)[-1].sort_by(bd.Axis.X)[0]
    body = bd.chamfer(outer_top, 1.0)
    step = body.edges().filter_by(bd.Axis.Y).group_by(bd.Axis.Z)[-1].sort_by(bd.Axis.X)[-1]
    body = bd.fillet(step, 0.3)
    by, bz = L.FLIPPER_Y - 20.0, 5.6
    bezel = bd.Pos(0, by, bz) * bd.Rot(0, 90, 0) * bd.Cylinder(4.4, 1.0, align=Z)
    hole = bd.Pos(0, by, bz) * bd.Rot(0, 90, 0) * bd.Cylinder(3.5, 8.0, align=Z)
    body = body - bezel - hole
    if side == "left":
        body = body - apron_slot(L.RAIL_W - APRON_TAB - 0.1, L.RAIL_W + 0.1)
    if side == "right":
        body = bd.mirror(body, bd.Plane.YZ.offset(L.BOARD_W / 2))
    return tag(body, f"rail_{side}", looks.mjf_black())


def lockdown_bar():
    """The lockdown bar across the front, flush with the glass's top: it holds the glass's front edge under
    a 2 mm lip; START on top, the plunger through its face; a 1.6 mm chamfer along its front."""
    w, d, h = L.BOARD_W, L.LOCKDOWN_D, L.GLASS_Z + L.GLASS_T
    body = bd.Pos(w / 2, d / 2, 0) * bd.Box(w, d, h, align=Z)
    front_top = body.edges().filter_by(bd.Axis.X).group_by(bd.Axis.Z)[-1].sort_by(bd.Axis.Y)[0]
    body = bd.chamfer(front_top, 1.6)
    body = bd.fillet(body.edges().filter_by(bd.Axis.Z), 1.0)
    groove = bd.Pos(w / 2, d - 1.0, L.GLASS_Z) * bd.Box(w - 2 * L.RAIL_W + 6.0, 2.0, L.GLASS_T, align=Z)
    start = cyl(w / 2, d / 2 - 0.6, h - 2.4, h + 1, 3.3)
    plunger = bd.Pos(L.SHOOTER_X, d / 2, 4.0) * bd.Rot(90, 0, 0) * bd.Cylinder(1.8, d + 2)
    body = body - groove - start - plunger
    return tag(body, "lockdown_bar", looks.mjf_black())


APRON_TAB = 1.0                             # mm the apron's ends reach into their slots


def apron():
    """The apron: a thin sculpted bridge over the ball's return (its underside 8.8 mm up, 0.8 mm over the
    ball), its edge curving under the flippers, two small boards inlaid as its cards. No feet: its ends sit in
    slots in the left rail and the shooter lane's wall, so the outlanes drain under it."""
    x0, x1 = L.RAIL_W - APRON_TAB, L.SHOOTER_WALL[0] + APRON_TAB
    y0, y1 = L.LOCKDOWN_D, L.APRON_Y[1]
    under, top_back, top_front = 8.8, 10.2, 10.6
    prof = [(y0, under), (y1, under), (y1, top_back - 0.3), (y1 - 1.5, top_back), (y0 + 3.0, top_front), (y0, top_front)]
    face = bd.Plane.YZ * bd.Polygon(*prof, align=None)
    body = bd.Pos(x0, 0, 0) * bd.extrude(face, amount=x1 - x0)
    keep = bd.Pos(L.CENTER_X, y1 - 160.0, -1) * bd.Cylinder(161.5, 20, align=Z)
    body = body & keep
    cy = (y0 + y1) / 2 + 0.5
    for cx in CARD_X:
        body = body - bd.Pos(cx, cy, top_back - 0.6) * bd.Box(22.0, 11.0, 6.0, align=Z)
    return tag(body, "apron", looks.mjf_black())


CARD_X = (L.RAIL_W + 15.5, L.SHOOTER_WALL[0] - 15.5)


def apron_slot(x0, x1):
    """The slot an apron's end sits in, cut from the rail or the wall between x0 and x1."""
    return bd.Pos((x0 + x1) / 2, (L.LOCKDOWN_D + L.APRON_Y[1]) / 2, 8.8) * bd.Box(
        x1 - x0, L.APRON_Y[1] - L.LOCKDOWN_D + 0.2, 10.6 - 8.8 + 0.4, align=Z)


def walls():
    """The shooter lane's wall, the top arch and the lane guides: MJF black, rounded tops."""
    out = []
    sw = fillet_top(slab(P.shooter_wall(), 0.0, 9.6), 0.75)
    sw = sw - apron_slot(L.SHOOTER_WALL[0] - 0.1, L.SHOOTER_WALL[0] + APRON_TAB + 0.1)
    out.append(tag(sw, "shooter_wall", looks.mjf_black()))
    rails = P.box(0, 0, L.RAIL_W, L.BOARD_L).union(P.box(L.BOARD_W - L.RAIL_W, 0, L.BOARD_W, L.BOARD_L))
    out.append(tag(slab(P.arch_wall().difference(rails), 0.0, 9.6), "top_arch", looks.mjf_black()))
    for side, g in P.lane_guides().items():
        g0, g1 = L.GUIDE_L if side == "left" else L.GUIDE_R
        g = g.difference(P.circle((g0 + g1) / 2, L.LANE_TOP_Y, L.POST_HEX_R + 1.05))
        out.append(tag(fillet_top(slab(g, 0.0, 8.0), 0.95), f"lane_guide_{side}", looks.mjf_black()))
    for i, g in enumerate(P.top_lane_guides()):
        c = g.centroid
        fin = bd.Pos(c.x, c.y, 0) * bd.Box(1.5, L.TOP_LANE_Y[1] - L.TOP_LANE_Y[0], 6.5, align=Z)
        fin = bd.fillet(fin.edges().filter_by(bd.Axis.Z), 0.74)
        fin = bd.fillet(fin.edges().group_by(bd.Axis.Z)[-1], 0.7)
        out.append(tag(fin, f"top_lane_guide_{i + 1}", looks.brass()))
    return out


def brass_post(x, y, h=9.0, label="post"):
    """A 4 mm hex brass standoff with a black rubber ring at the ball's equator."""
    post = hexagon(x, y, 0.0, h, 4.0)
    ring = bd.Pos(x, y, L.BALL_R) * bd.Torus(L.POST_HEX_R + 0.5, 0.5)
    return [tag(post, label, looks.brass()), tag(ring, label + "_rubber", looks.rubber_orange())]


def lane_posts():
    out = []
    for side, (g0, g1) in (("left", L.GUIDE_L), ("right", L.GUIDE_R)):
        out += brass_post((g0 + g1) / 2, L.LANE_TOP_Y, label=f"lane_post_{side}")
    return out


# ============================================================================================ furniture

def _hull_band(posts, r_centre, rad, z):
    """A rubber band of round section `rad` round posts (a convex hull path at r_centre from each post's
    centre): torus arcs at the posts, tubes between them."""
    pts = list(posts)
    n = len(pts)
    # winding: counter-clockwise
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    if area < 0:
        pts = pts[::-1]
    parts = []
    normals = []
    for i in range(n):
        (ax, ay), (bx, by) = pts[i], pts[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        ln = math.hypot(dx, dy)
        nx, ny = dy / ln, -dx / ln              # outward (right of a CCW edge)
        normals.append((nx, ny))
        a = (ax + nx * r_centre, ay + ny * r_centre)
        b = (bx + nx * r_centre, by + ny * r_centre)
        tube = bd.Solid.make_cylinder(rad, ln, bd.Plane(origin=(a[0], a[1], z), z_dir=(dx / ln, dy / ln, 0)))
        parts.append(tube)
    for i in range(n):
        n_in = normals[i - 1]
        n_out = normals[i]
        a0 = math.degrees(math.atan2(n_in[1], n_in[0]))
        a1 = math.degrees(math.atan2(n_out[1], n_out[0]))
        sweep = (a1 - a0) % 360
        x, y = pts[i]
        torus = bd.Solid.make_torus(r_centre, rad, bd.Plane((x, y, z)), 0, 360, sweep)   # sweep: the major arc
        parts.append(torus.rotate(bd.Axis((x, y, z), (0, 0, 1)), a0))
    return bd.Compound(parts)


def sling(side: str, lit: bool = False):
    """A slingshot: three brass hex posts, the orange band round them, and on top, where a real machine has
    a printed plastic, a 1.2 mm board: black soldermask, a gold rim and a gold arrow of dots, an LED under."""
    posts = P.sling_posts(side)
    out = []
    for i, (x, y) in enumerate(posts):
        out.append(tag(hexagon(x, y, 0.0, 8.6, 4.0), f"sling_{side}_post_{i + 1}", looks.brass()))
    band = _hull_band(posts, L.POST_HEX_R + 0.9, 0.9, L.BALL_R)
    out.append(tag(band, f"sling_{side}_rubber", looks.rubber_orange()))
    base = P.unary_union([P.circle(x, y, 0.1) for x, y in posts]).convex_hull.buffer(0.9, quad_segs=8)
    plinth = slab(base, 0.0, 1.6) - bd.Compound([hexagon(x, y, -0.1, 1.7, 4.0) for x, y in posts])
    out.append(tag(plinth, f"sling_{side}_plinth", looks.mjf_black()))
    cap = P.unary_union([P.circle(x, y, L.POST_R + 2.0) for x, y in posts]).convex_hull
    out.append(tag(slab(cap, 8.6, 9.8), f"sling_{side}_board", looks.soldermask()))
    rim = cap.buffer(-0.5, quad_segs=8).boundary.buffer(0.22, quad_segs=6)
    out.append(tag(slab(rim, 9.8, 9.835), f"sling_{side}_gold", looks.enig()))
    edge = cap.buffer(0.04, quad_segs=8).difference(cap)
    out.append(tag(slab(edge, 8.6, 9.8), f"sling_{side}_edge", looks.enig()))
    (x0, y0), (x1, y1), (x2, y2) = posts
    cx, cy = (x0 + x1 + x2) / 3, (y0 + y1 + y2) / 3
    ang = math.degrees(math.atan2(y2 - y0, x2 - x0)) + (90.0 if side == "left" else -90.0)
    arrow = [(cx + 2.4 * math.cos(math.radians(ang)) * k + 1.1 * j * math.cos(math.radians(ang + 90)),
              cy + 2.4 * math.sin(math.radians(ang)) * k + 1.1 * j * math.sin(math.radians(ang + 90)), 0.7)
             for k, j in ((1, 0), (0, -1), (0, 1), (-1, -2), (-1, 2))]
    out.append(tag(dots(arrow, 9.8, 0.035), f"sling_{side}_dots", looks.enig()))
    for i, (x, y) in enumerate(posts):
        head = bd.Pos(x, y, 9.8) * bd.Cylinder(2.0, 0.45, align=Z)
        head = bd.fillet(head.edges().group_by(bd.Axis.Z)[-1], 0.4)
        out.append(tag(head, f"sling_{side}_screw_{i + 1}", looks.brass()))
    out.append(tag(bd.Pos(cx, cy, 1.6) * bd.Box(2.0, 2.0, 0.85, align=Z), f"sling_{side}_led", looks.led(lit)))
    return out


def bumper(name: str, lit: bool = False):
    """A bumper: a black post with an orange O-ring at the ball's equator, a brass collar, and a domed cap of
    clear amber resin with a sharp edge, lit from inside by the LED under the post's bore."""
    x, y = L.BUMPERS[name]
    post = bd.Cylinder(L.BUMPER_POST_R, 6.6, align=Z)
    groove = bd.Pos(0, 0, L.BALL_R - 0.85) * (bd.Cylinder(L.BUMPER_POST_R + 1, 1.7, align=Z) - bd.Cylinder(L.BUMPER_POST_R - 0.6, 1.7, align=Z))
    bore = bd.Cylinder(1.6, 7.0, align=Z)
    pocket = bd.Box(2.8, 2.8, 1.3, align=Z)
    post = post - groove - bore - pocket
    oring = bd.Pos(x, y, L.BALL_R) * bd.Torus(L.BUMPER_POST_R - 0.6 + 0.8, 0.8)
    collar = bd.Pos(x, y, 6.6) * (bd.Cylinder(6.3, 0.7, align=Z) - bd.Cylinder(1.6, 0.7, align=Z))
    dome_r = 12.0
    cap = bd.Cylinder(6.0, 1.8, align=Z) + bd.Pos(0, 0, 2.7 - dome_r) * bd.Sphere(dome_r) & \
        bd.Cylinder(6.0, 2.7, align=Z)
    cap = bd.Pos(x, y, 7.3) * cap
    led = bd.Pos(x, y, 0) * bd.Box(2.0, 2.0, 0.85, align=Z)
    return [tag(bd.Pos(x, y, 0) * post, f"bumper_{name}_post", looks.mjf_black()),
            tag(collar, f"bumper_{name}_collar", looks.brass()),
            tag(cap, f"bumper_{name}", looks.crystal(lit)), tag(oring, f"bumper_{name}_rubber", looks.rubber_orange()),
            tag(led, f"bumper_{name}_led", looks.led(lit))]


def target(name: str, lit: bool = False):
    """A standup target: an FR-4 card standing in a slot in the playfield, its face ENIG (the ball hits gold),
    its back black, a black post behind it and an LED that lights its edge."""
    y = L.TARGETS[name]
    fx = L.TARGET_FACE_X
    t = L.TARGET_T
    post = bd.Pos((L.RAIL_W + fx - t) / 2, y, 0) * bd.Box(fx - t - L.RAIL_W, 4.0, 7.6, align=Z)
    post = fillet_top(post, 0.8)
    post = post - bd.Pos(fx - 3.4, y, -0.1) * bd.Box(2.1, 2.1, 1.0, align=Z)
    card = bd.Pos(fx - t / 2, y, 0) * bd.Box(t, L.TARGET_W, L.TARGET_H, align=Z)
    card = bd.fillet(card.edges().filter_by(bd.Axis.X).group_by(bd.Axis.Z)[-1], 1.4)
    face = bd.Pos(fx + 0.0175, y, 0.4) * bd.Box(0.035, L.TARGET_W - 1.2, L.TARGET_H - 1.2, align=Z)
    face = bd.fillet(face.edges().filter_by(bd.Axis.X).group_by(bd.Axis.Z)[-1], 0.9)
    led = bd.Pos(fx - 3.4, y, 0) * bd.Box(2.0, 2.0, 0.85, align=Z)
    return [tag(post, f"target_{name}_post", looks.mjf_black()), tag(card, f"target_{name}_card", looks.soldermask()),
            tag(face, f"target_{name}", looks.enig()), tag(led, f"target_{name}_led", looks.led(lit))]


def _bat_face(offset=0.0):
    with bd.BuildSketch() as sk:
        with bd.Locations((0, 0)):
            bd.Circle(L.FLIPPER_RB + offset)
        with bd.Locations((L.FLIPPER_L, 0)):
            bd.Circle(L.FLIPPER_RT + offset)
        bd.make_hull()
    return sk.sketch


def flipper_bat():
    """A bat at the origin pointing +x, a stack of three boards: 2.0 mm, 1.6 mm (inset 0.9 mm: the rubber's
    groove), 2.0 mm; black soldermask, every edge plated in gold, a gold ring round the pivot on top."""
    layers = [(L.FLIPPER_Z0, 2.0, 0.0), (L.FLIPPER_Z0 + 2.0, 1.6, -0.9), (L.FLIPPER_Z0 + 3.6, 2.0, 0.0)]
    boards, edges = [], []
    for z, h, off in layers:
        f = _bat_face(off)
        boards.append(bd.Pos(0, 0, z) * bd.extrude(f, h) - bd.Pos(0, 0, z - 0.1) * bd.Cylinder(1.5, h + 0.2, align=Z))
        edges.append(bd.Pos(0, 0, z) * (bd.extrude(_bat_face(off + 0.04), h) - bd.extrude(f, h)))
    return boards, edges


def flipper_rubber():
    """The flipper's rubber: an orange O-ring (1.6 mm section) in the stack's groove."""
    zc = L.FLIPPER_Z0 + 2.0 + 0.8
    band = bd.Pos(0, 0, zc - 0.8) * (bd.extrude(_bat_face(-0.9 + L.RUBBER_CS), 1.6) - bd.extrude(_bat_face(-0.9), 1.6))
    try:
        band = bd.fillet(band.edges().group_by(bd.Axis.Z)[-1] + band.edges().group_by(bd.Axis.Z)[0], 0.7)
    except Exception:
        pass
    return band


def flipper(side: str, angle: float | None = None):
    a = L.FLIPPER_REST if angle is None else angle
    if side == "right":
        a = 180.0 - a
    px, py = L.PIVOTS[side]
    place = bd.Pos(px, py, 0) * bd.Rot(0, 0, a)
    boards, edges = flipper_bat()
    out = [tag(place * bd.Compound(boards), f"flipper_{side}", looks.soldermask()),
           tag(place * bd.Compound(edges), f"flipper_{side}_edge", looks.enig()),
           tag(place * flipper_rubber(), f"flipper_{side}_rubber", looks.rubber_orange())]
    top = L.FLIPPER_Z0 + 5.6
    ring = bd.Pos(px, py, top) * (bd.Cylinder(3.0, 0.035, align=Z) - bd.Cylinder(2.3, 0.035, align=Z))
    out.append(tag(ring, f"flipper_{side}_ring", looks.enig()))
    out.append(tag(bd.Pos(px, py, top) * bd.Cylinder(1.9, 0.5, align=Z), f"flipper_{side}_cap", looks.brass()))
    return out


def plunger():
    """The spring plunger at the front right: an orange knob, a brass rod through the lockdown bar, a black
    rubber tip in the lane, and a close-wound chrome extension spring hooked between the bushing and the rod's
    collar: pulling the knob stretches it (its coils open), letting go snaps the tip into the ball."""
    x, z = L.SHOOTER_X, 4.0
    axis = bd.Plane(origin=(x, 0, z), z_dir=(0, -1, 0))       # out of the bar's face, toward the player
    rod = bd.Solid.make_cylinder(1.5, 30.0, bd.Plane(origin=(x, L.PLUNGER_REST_Y - 1.0, z), z_dir=(0, -1, 0)))
    bush = bd.Solid.make_cylinder(3.2, 2.0, axis)
    knob_body = bd.Solid.make_cylinder(4.8, 7.0, axis.offset(13.0))
    knob = bd.fillet(knob_body.edges(), 2.2)
    collar = bd.Solid.make_cylinder(2.6, 1.2, axis.offset(11.8))
    helix = bd.Helix(pitch=0.43, height=9.25, radius=2.75, center=(0, 0, 0))     # 0.42 mm wire, close-wound
    profile = bd.Plane(origin=helix @ 0, z_dir=helix % 0) * bd.Circle(0.21)
    spring = axis.offset(2.35).location * bd.sweep(profile, path=helix)
    tip = bd.Solid.make_cylinder(2.4, 2.0, bd.Plane(origin=(x, L.PLUNGER_REST_Y, z), z_dir=(0, -1, 0)))
    bush, knob, collar, tip = (bush - rod), (knob - rod), (collar - rod), (tip - rod)
    return [tag(rod, "plunger_rod", looks.brass()), tag(bush, "plunger_bushing", looks.brass()),
            tag(knob, "plunger_knob", looks.orange_resin()), tag(collar, "plunger_collar", looks.brass()),
            tag(spring, "plunger_spring", looks.chrome()), tag(tip, "plunger_tip", looks.rubber_black())]


def buttons(lit: bool = False):
    """The flipper buttons in the rails' faces and START on the lockdown bar: signal orange, domed."""
    out = []
    by, bz = L.FLIPPER_Y - 20.0, 5.6
    for side, x, sign in (("left", 0.0, -1), ("right", L.BOARD_W, 1)):
        cap = bd.Solid.make_cylinder(3.4, 3.2, bd.Plane(origin=(x - sign * 0.8, by, bz), z_dir=(sign, 0, 0)))
        cap = bd.fillet(cap.edges().sort_by(bd.SortBy.DISTANCE, reverse=False)[-1:], 1.2) if False else cap
        out.append(tag(cap, f"flipper_button_{side}", looks.orange_resin()))
        ring = bd.Solid.make_cylinder(4.3, 0.6, bd.Plane(origin=(x - sign * 1.0, by, bz), z_dir=(sign, 0, 0))) - \
            bd.Solid.make_cylinder(3.6, 0.6, bd.Plane(origin=(x - sign * 1.0, by, bz), z_dir=(sign, 0, 0)))
        out.append(tag(ring, f"flipper_button_{side}_bezel", looks.brass()))
    sx, sy = L.BOARD_W / 2, L.LOCKDOWN_D / 2 - 0.6
    htop = L.GLASS_Z + L.GLASS_T
    start = bd.Pos(sx, sy, htop - 2.0) * bd.Cylinder(3.0, 3.0, align=Z)
    start = bd.fillet(start.edges().group_by(bd.Axis.Z)[-1], 1.0)
    out.append(tag(start, "start_button", looks.orange_resin()))
    ring = bd.Pos(sx, sy, htop) * (bd.Cylinder(4.4, 0.4, align=Z) - bd.Cylinder(3.3, 0.4, align=Z))
    out.append(tag(ring, "start_bezel", looks.brass()))
    return out


def glass():
    y0, y1 = L.LOCKDOWN_D - 2.0, L.BACKBOX_Y - 2.5
    g = bd.Pos(L.BOARD_W / 2, (y0 + y1) / 2, L.GLASS_Z) * bd.Box(L.BOARD_W - L.RAIL_W - 0.4, y1 - y0, L.GLASS_T, align=Z)
    return tag(g, "glass", looks.glass())


def ball(x, y):
    return tag(bd.Pos(x, y, L.BALL_R) * bd.Sphere(L.BALL_R), "ball", looks.chrome())


# ============================================================================================ under the board

def solenoid(label: str):
    """Takaha CA0730 open-frame pull solenoid, from its catalogue drawing: an 18 x 19 mm frame, 30.7 mm
    long with the plunger in, a 7 mm plunger with a 3 mm cross hole. Built along +y (the plunger's pull),
    its mounting face (two M3 tapped holes) up at z = 0."""
    frame = bd.Pos(0, 13.0, -9.0) * bd.Box(19.0, 22.0, 18.0)
    frame = frame - bd.Pos(0, 13.0, -9.0) * bd.Box(15.8, 22.2, 15.0)
    coil = bd.Solid.make_cylinder(7.2, 18.0, bd.Plane(origin=(0, 4.0, -9.0), z_dir=(0, 1, 0))) - \
        bd.Solid.make_cylinder(3.6, 18.0, bd.Plane(origin=(0, 4.0, -9.0), z_dir=(0, 1, 0)))
    tape = bd.Solid.make_cylinder(7.35, 6.0, bd.Plane(origin=(0, 10.0, -9.0), z_dir=(0, 1, 0))) - \
        bd.Solid.make_cylinder(7.2, 6.0, bd.Plane(origin=(0, 10.0, -9.0), z_dir=(0, 1, 0)))
    plunger = bd.Solid.make_cylinder(3.5, 11.0, bd.Plane(origin=(0, -6.0, -9.0), z_dir=(0, 1, 0)))
    plunger = plunger - bd.Solid.make_cylinder(1.5, 8.0, bd.Plane(origin=(0, -4.0, -13.0), z_dir=(0, 0, 1)))
    return [tag(frame, f"{label}_frame", looks.zinc()), tag(coil, f"{label}_coil", looks.copper_wire()),
            tag(tape, f"{label}_tape", looks.component_black()), tag(plunger, f"{label}_plunger", looks.steel())]


def flipper_mech(side: str):
    """Under a flipper: the shaft in two bearings, the bracket, the crank and link, the solenoid pulling
    toward the back, the return spring."""
    px, py = L.PIVOTS[side]
    s = 1 if side == "left" else -1
    zb = -L.BOARD_T
    out = []
    shaft = cyl(px, py, -17.0, L.FLIPPER_Z0 + 5.0, 1.5)
    out.append(tag(shaft, f"{side}_shaft", looks.steel()))
    bearings = []
    for z in (zb - 0.6, zb - 4.6):
        b = cyl(px, py, z, z + 0.6, 3.6) + cyl(px, py, z - 1.9, z, 3.0)
        bearings.append(b)
        out.append(tag(b - shaft, f"{side}_bearing", looks.steel()))
    # the bracket: a plate under the board from the shaft back over the solenoid (clear of the inlane lamp)
    plate = bd.Pos(px + s * 6.0, py + 16.0, zb - 3.0) * bd.Box(22.0, 40.0, 3.0, align=Z)
    plate = bd.fillet(plate.edges().filter_by(bd.Axis.Z), 3.0) - bearings[0] - shaft
    out.append(tag(plate, f"{side}_bracket", looks.mjf_black()))
    # the solenoid hanging from it, pulling +y
    sol_x, sol_y = px + s * 4.4, py + 11.0
    for part in solenoid(f"{side}_solenoid"):
        out.append(tag(bd.Pos(sol_x, sol_y, zb - 3.0) * part, part.label, part.material))
    # crank on the shaft at the plunger's height, a link to the plunger's cross pin
    zc = zb - 3.0 - 9.0
    crank = bd.Pos(px, py, zc - 1.0) * (bd.Cylinder(3.2, 2.0, align=Z) + bd.Pos(s * 2.2, 0, 0) * bd.Box(4.4, 4.0, 2.0, align=Z))
    out.append(tag(crank - shaft, f"{side}_crank", looks.steel()))
    link = bd.Pos(sol_x, (py + sol_y + 5.0) / 2, zc - 0.6) * bd.Box(2.4, sol_y - 5.0 - py + 2.0, 1.2, align=Z)
    out.append(tag(link, f"{side}_link", looks.steel()))
    helix = bd.Helix(pitch=0.7, height=9.0, radius=1.1)
    prof = bd.Plane(origin=helix @ 0, z_dir=helix % 0) * bd.Circle(0.22)
    spring = bd.Pos(px - s * 3.6, py + 1.0, zc) * bd.Rot(-90, 0, 0) * bd.sweep(prof, path=helix)
    out.append(tag(spring, f"{side}_return_spring", looks.steel()))
    return out


def underside_parts(lit: bool = False):
    """The board's underside, as the layout will populate it (stand-ins until the board is laid out):
    the RP2040 and its flash, the power stage, the coil drivers, connectors, the inserts' reverse-mount
    LEDs, the underglow LEDs. Each a block of its package's size."""
    zb = -L.BOARD_T
    out = []

    def chip(label, x, y, w, d, h, mat):
        out.append(tag(bd.Pos(x, y, zb - h) * bd.Box(w, d, h, align=Z), label, mat))

    cx = L.CENTER_X
    chip("u_rp2040", cx, 158.0, 7.0, 7.0, 0.9, looks.component_black())
    chip("u_flash", cx - 13.0, 158.0, 5.0, 4.0, 1.6, looks.component_black())
    chip("y_crystal", cx + 13.0, 158.0, 3.2, 2.5, 0.8, looks.zinc())
    chip("u_amp", cx + 15.0, 172.0, 3.0, 3.0, 0.8, looks.component_black())
    chip("u_accel", cx - 15.0, 172.0, 3.0, 3.0, 1.0, looks.component_black())
    chip("u_pd", cx + 6.0, 214.0, 4.9, 3.9, 1.5, looks.component_black())
    chip("u_buck", cx - 6.0, 214.0, 3.0, 2.9, 1.2, looks.component_black())
    chip("l_buck", cx - 13.0, 214.0, 4.0, 4.0, 2.0, looks.component_black())
    chip("u_ldo", cx - 20.0, 205.0, 3.0, 3.0, 1.1, looks.component_black())
    out.append(tag(cyl(cx + 18.0, 212.0, zb - 10.2, zb, 4.0), "c_bulk", looks.steel()))
    for i, s in enumerate((-1, 1)):
        chip(f"q_coil_{i + 1}", cx + s * 14.0, 100.0, 2.9, 2.4, 1.0, looks.component_black())
        chip(f"d_flyback_{i + 1}", cx + s * 14.0, 106.0, 4.3, 2.6, 2.1, looks.component_black())
        chip(f"j_coil_{i + 1}", cx + s * 20.0, 90.0, 6.0, 4.5, 6.0, looks.led_white())
    chip("j_backbox", cx + 26.0, 206.0, 6.0, 4.2, 2.9, looks.led_white())
    chip("j_usb", cx, L.BOARD_L - 3.6, 8.9, 7.3, 3.2, looks.zinc())
    # passives in rows round the MCU and the power stage
    for k in range(14):
        a = 2 * math.pi * k / 14
        chip(f"c_dec_{k}", cx + 7.5 * math.cos(a), 158.0 + 7.5 * math.sin(a), 1.0, 0.5, 0.5, looks.ceramic_tan())
    for k in range(10):
        chip(f"r_sense_{k}", cx - 20.0 + 4.4 * k, 130.0, 1.6, 0.8, 0.5, looks.component_black())
    # each insert's reverse-mount RGB LED (SK6812MINI-E), its body under the board
    art = P.build_art()
    for name, (x, y) in art.leds.items():
        chip(f"led_{name.lower()}", x, y, 3.2, 2.8, 1.78, looks.led_white())
    # underglow: six LEDs down each long edge, facing into the engine room (they light it through the
    # smoked sides)
    for i in range(6):
        for side, x in (("l", 8.0), ("r", L.BOARD_W - 8.0)):
            chip(f"led_underglow_{side}{i + 1}", x, 34.0 + 30.0 * i, 3.2, 2.8, 1.0, looks.led(lit))
    return out


# ============================================================================================ the backbox

BB_W, BB_H = L.BACKGLASS_W, L.BACKGLASS_H   # the backglass board: across, up (built flat, then stood up)
DMD_COLS, DMD_ROWS, DMD_PITCH = 39, 9, 2.6  # the display: 39 x 9 orange LEDs, 101 x 23 mm
DMD_CENTRE = (BB_W / 2, 31.0)               # on the backglass, from its bottom edge
STANDOFFS = ((7.0, 7.0), (BB_W - 7.0, 7.0), (7.0, BB_H - 7.0), (BB_W - 7.0, BB_H - 7.0))
BB_BASE = 4.0                               # the backglass's bottom edge above the playfield


def _stand(shape, depth=0.0):
    """Backglass-local (u across, v up, w out of its face toward the player) -> the playfield frame, the
    board's face at y = BACKBOX_Y (it is stood upright in machine.py)."""
    return bd.Pos(0, L.BACKBOX_Y - depth, BB_BASE) * bd.Rot(90, 0, 0) * shape


def backbox_parts(lit: bool = False, dmd_text: str = "SHORT CIRCUIT"):
    """The head: the backglass is a bare 1.6 mm board (black, gold edge-plated, its title drawn as copper
    traces, the 39 x 9 display as a full-width band, the display's wiring fanned out in gold below it)
    standing on four brass standoffs in front of a shallow black tray that holds the speaker and the driver;
    a black base rail under both."""
    import dotfont
    out = []
    W, H = BB_W, BB_H
    pcb = bd.Box(W, H, 1.6, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MAX))
    pcb = bd.fillet(pcb.edges().filter_by(bd.Axis.Z), 2.5)
    holes = [bd.Pos(u, v, -2) * bd.Cylinder(1.6, 4, align=Z) for u, v in STANDOFFS]
    out.append(tag(_stand(pcb - bd.Compound(holes)), "backglass_pcb", looks.soldermask()))
    rim = bd.fillet(bd.Box(W + 0.08, H + 0.08, 1.6, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MAX)).edges().filter_by(bd.Axis.Z), 2.54)
    rim = bd.Pos(-0.04, -0.04, 0) * rim - pcb
    out.append(tag(_stand(rim), "backglass_edge", looks.enig()))
    gold = []
    # the frame line, and gold rings round the standoffs' holes
    gold.append(P.rounded_rect(2.6, 2.6, W - 2.6, H - 2.6, 1.6).boundary.buffer(0.22))
    for u, v in STANDOFFS:
        gold.append(P.ring(u, v, 1.9, 3.4))
    # fiducials: a gold dot in a clear ring, as an assembler's camera looks for them
    for u, v in ((W - 13.0, 9.5), (13.0, H - 13.0)):
        gold.append(P.circle(u, v, 0.5))
    # the title, drawn as copper traces with a via at every end
    vias = []
    for text, v in (("SHORT", H - 26.0), ("CIRCUIT", H - 50.0)):
        segs, ends = dotfont.placed_strokes(text, 2.35, (W / 2, v))
        for a_, b_ in segs:
            gold.append(P.stroke([a_, b_], 1.05))
        for u, vv in ends:
            gold.append(P.ring(u, vv, 0.32, 0.95))
            vias.append((u, vv))
    # the display's columns fanned out below it as gold traces to a row of vias over the driver
    cu, cv = DMD_CENTRE
    bottom = cv - (DMD_ROWS - 1) / 2 * DMD_PITCH - 2.2
    for c in range(DMD_COLS):
        u0 = cu + (c - (DMD_COLS - 1) / 2) * DMD_PITCH
        u1 = cu + (c - (DMD_COLS - 1) / 2) * 1.05
        drop = 3.0
        knee = bottom - drop - abs(u0 - u1)
        pts = [(u0, bottom), (u0, bottom - drop), (u1, knee), (u1, 9.0)]
        gold.append(P.stroke(pts, 0.3, cap="round"))
        gold.append(P.ring(u1, 9.0 - 0.4, 0.15, 0.42))
    gold.append(P.rounded_rect(cu - DMD_COLS * DMD_PITCH / 2 - 1.2, cv - DMD_ROWS * DMD_PITCH / 2 - 1.2,
                               cu + DMD_COLS * DMD_PITCH / 2 + 1.2, cv + DMD_ROWS * DMD_PITCH / 2 + 1.2, 1.2).boundary.buffer(0.2))
    gold_geom = P.unary_union(gold)
    out.append(tag(_stand(slab(gold_geom, 0.0, 0.035)), "backglass_gold", looks.enig()))
    # silkscreen: the tagline and the small print
    silk = [(u, v, 0.3) for u, v in dotfont.placed("THE BALL IS THE SWITCH", 0.46, (W / 2, H - 64.0))]
    silk += [(u, v, 0.26) for u, v in dotfont.placed("SC-BB REV A", 0.4, (13.0, 4.8), anchor="left")]
    silk += [(u, v, 0.26) for u, v in dotfont.placed("U1 IS31FL3741", 0.4, (W - 13.0, 4.8), anchor="right")]
    out.append(tag(_stand(dots(silk, 0.0, 0.02)), "backglass_silk", looks.silkscreen()))
    # the display: 1.6 mm square orange LEDs, the text lit where a frame of it would be
    lit_cells = set()
    if lit:
        lit_cells = {(round(u, 2), round(v, 2)) for u, v in dotfont.placed(dmd_text[:6], DMD_PITCH, (cu, cv))}
    on, off = [], []
    for c in range(DMD_COLS):
        for r in range(DMD_ROWS):
            u = cu + (c - (DMD_COLS - 1) / 2) * DMD_PITCH
            v = cv + (r - (DMD_ROWS - 1) / 2) * DMD_PITCH
            cell = bd.Pos(u, v, 0) * bd.Box(1.6, 1.6, 0.55, align=Z)
            (on if (round(u, 2), round(v, 2)) in lit_cells else off).append(cell)
    if on:
        out.append(tag(_stand(bd.Compound(on)), "dmd_lit", looks.dmd_dot(True)))
    out.append(tag(_stand(bd.Compound(off)), "dmd", looks.dmd_dot(False)))
    # the standoffs (brass hex, M3 x 10) behind, their screws' heads in front
    for u, v in STANDOFFS:
        sto = bd.Pos(u, v, -1.6 - L.STANDOFF_L) * bd.extrude(bd.RegularPolygon(5.5 / math.sqrt(3), 6), L.STANDOFF_L)
        out.append(tag(_stand(sto), "backglass_standoff", looks.brass()))
        head = bd.Pos(u, v, 0) * bd.Cylinder(2.75, 1.65, align=Z)
        head = bd.fillet(head.edges().group_by(bd.Axis.Z)[-1], 1.2)
        out.append(tag(_stand(head), "backglass_screw", looks.brass()))
    # the head behind: a black shell the board's own size and outline, 22 mm deep behind the standoffs, its
    # back edges eased; a row of speaker slots across its top
    t0 = 1.6 + L.STANDOFF_L
    depth = L.BACKBOX_D - t0
    shell = bd.Box(W, H, depth, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MAX))
    shell = bd.fillet(shell.edges().filter_by(bd.Axis.Z), 2.5)
    shell = bd.Pos(0, 0, -t0) * bd.fillet(shell.edges().group_by(bd.Axis.Z)[0], 1.6)
    slots = [bd.Pos(W / 2 + (k - 5) * 4.2, H, -t0 - depth / 2) * bd.Box(1.6, 2.4, depth - 8.0) for k in range(11)]
    slots = [bd.fillet(sl.edges().filter_by(bd.Axis.Y), 0.79) for sl in slots]
    shell = shell - bd.Compound(slots)
    out.append(tag(_stand(shell), "backbox_shell", looks.mjf_black()))
    # the base rail the board and the shell stand on
    base = bd.Pos(W / 2, (L.BACKBOX_Y - 1.5 + L.BOARD_L) / 2, 0) * bd.Box(W, L.BOARD_L - L.BACKBOX_Y + 1.5, BB_BASE, align=Z)
    base = bd.chamfer(base.edges().filter_by(bd.Axis.X).group_by(bd.Axis.Z)[-1].sort_by(bd.Axis.Y)[0], 1.2)
    out.append(tag(base, "backbox_base", looks.mjf_black()))
    return out
