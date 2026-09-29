"""Pistons: nine forged-aluminium pistons, six rings each, full-floating wrist pins.

Authored ONCE in a piston-local frame (wrist-pin centre at the origin, +Z = the
cylinder axis toward the head, pin axis along +Y = the crank axis, X = the
cylinder's tangential t), then placed on every cylinder at its theta = 0
wrist-pin height kin.piston_h(0, k) with geo.cyl_location(k). All nine share
one geometry per part.

Piston (spec): bore 146, compression height 58 (pin centre -> crown flat),
4 mm crown dome, skirt 64 below the pin. Ring belt (R-1340 practice): three
compression rings near the crown, two slotted oil-control rings (one above the
pin, one below), one bevelled scraper at the skirt foot. Inside: a forged
underside with two pin bosses hung from the crown on drafted webs, a rib grid
under the crown, pin-boss inner faces at |y| = 19 (rod small ends |y| <= 17).
"""

from __future__ import annotations

import math

from cadgen import build123d as bd

from lib import castings as C
from lib import geo
from lib import kin
from lib import palette as P
from lib import spec as S

MATERIALS = ("cast_alu", "machined_alu", "section_red", "steel_dark", "steel_machined")

# ---------------------------------------------------------------------------
# Numbers (piston-local, mm; z from the wrist-pin centre)
# ---------------------------------------------------------------------------
R_BORE = S.BORE / 2.0                       # 73.0
Z_CROWN = S.PISTON_COMPRESSION_H            # 58: crown flat
Z_DOME = Z_CROWN + S.PISTON_DOME            # 62: dome apex
Z_FOOT = -S.PISTON_SKIRT_BELOW_PIN          # -64: skirt foot
R_DOME = 63.0                               # dome footprint radius (flat squish annulus outside)
R_SKIRT = R_BORE - 0.3                      # 145.4 skirt: 0.6 mm under bore (a visible gap, no z-fight)
R_TOPLAND = (R_BORE - 0.75, R_BORE - 0.6)   # top land tapers 144.5 -> 144.8
LAND_R = (R_BORE - 0.5, R_BORE - 0.45, R_BORE - 0.4)   # lands between the compression grooves
R_RING_OD = R_BORE - 0.25                   # rings just proud of the skirt; a dark 0.25 line to the bore in section
EDGE_C = 0.3                                # groove/land edge break

# (name, z_top, z_bottom, groove root radius)
# The whole six-ring pack sits ABOVE the pin: below z ~ 14.6 the skirt is trimmed
# to the cylinder wedge (see piston_body), where no full-circle ring can live.
GROOVES = (
    ("c1", 51.0, 48.6, 67.3),       # 7 mm top land
    ("c2", 46.0, 43.6, 67.3),
    ("c3", 41.0, 38.6, 67.3),
    ("o1", 36.0, 32.0, 67.9),       # dual slotted oil-control rings
    ("o2", 29.4, 25.4, 67.9),
    ("s", 22.8, 20.4, 69.3),        # taper-faced scraper, lowest in the pack
)
H_BDC_MIN = 188.75                          # lowest BDC wrist-pin height of any cylinder (kin.report)

R_IN = 64.0                                 # cavity radius (skirt and ring belt: one clean bore)
Z_UNDER = 44.0                              # crown underside
PIN_BORE_R = S.WRIST_PIN_D / 2.0 + 0.25     # visible running gap round the pin (no coincident faces)
BOSS_R = 29.0
BOSS_Y0 = S.PISTON_PIN_BOSS_INNER_Y         # 19

PIN_R = S.WRIST_PIN_D / 2.0                 # 19
PIN_ID_R = 12.0
PIN_HALF = 66.0
PLUG_APEX = R_SKIRT - 0.3                   # 72.4: pin assembly 144.8 long, just under the skirt
RING_SIDE = 0.25                            # ring side clearance (each face): the groove reads in section
RING_BACK = 1.5                             # back clearance: a dark groove root behind each ring in section
# slipper skirt (thrust sides relieved to vertical flats; the whole piston then
# stays inside its 40 deg cylinder wedge at the lowest BDC, geo.wedge_trim)
FLAT_T = 44.0                               # |t| of the outer flats (wedge allows 44.3 at the foot)
FLAT_WALL = 4.0                             # flat wall thickness
Z_SHOULDER = 15.0                           # flats end here; full circle above (wedge needs >= 13.9)
NOTCH_HW, NOTCH_TOP = 22.0, -44.0           # arched rod-relief notch at the foot of each flat


# ---------------------------------------------------------------------------
# Profile helper: revolve an (r, z) outline about local Z, arcs where asked
# ---------------------------------------------------------------------------
def _pt(r, z):
    return bd.Vector(r, 0.0, z)


def _revolve_rz(items, arc=360.0):
    """items: [(r, z)] or ("arc", (rm, zm), (r, z)) closed back to the first point.
    The outline lies in the XZ half-plane x >= 0 and is revolved about Z."""
    edges = []
    start = items[0]
    cur = _pt(*start)
    for it in items[1:] + [start]:
        if isinstance(it, tuple) and len(it) == 3 and it[0] == "arc":
            _, mid, end = it
            nxt = _pt(*end)
            edges.append(bd.ThreePointArc(cur, _pt(*mid), nxt))
        else:
            nxt = _pt(*it)
            if (nxt - cur).length < 1e-9:
                continue
            edges.append(bd.Line(cur, nxt))
        cur = nxt
    face = bd.make_face(bd.Wire(edges))
    return bd.revolve(face, axis=bd.Axis.Z, revolution_arc=arc)


def _arc_mid(c, r, a0, a1):
    a = math.radians((a0 + a1) / 2.0)
    return (c[0] + r * math.cos(a), c[1] + r * math.sin(a))


# ---------------------------------------------------------------------------
# Piston body
# ---------------------------------------------------------------------------
def _piston_outline():
    c = EDGE_C
    Rs = (R_DOME ** 2 + S.PISTON_DOME ** 2) / (2 * S.PISTON_DOME)
    zc = Z_DOME - Rs
    rm = R_DOME / 2.0
    pts = [(0.0, Z_DOME),
           ("arc", (rm, zc + math.sqrt(Rs * Rs - rm * rm)), (R_DOME, Z_CROWN)),
           (R_TOPLAND[0] - 0.9, Z_CROWN),
           (R_TOPLAND[0], Z_CROWN - 0.9)]
    # land radius ABOVE each groove, and BELOW it
    above = [R_TOPLAND[1], LAND_R[0], LAND_R[1], LAND_R[2], LAND_R[2], LAND_R[2]]
    for i, (_, zt, zb, root) in enumerate(GROOVES):
        ra = above[i]
        rb = above[i + 1] if i + 1 < len(GROOVES) else R_SKIRT
        pts += [(ra, zt + c), (ra - c, zt), (root, zt), (root, zb), (rb - c, zb), (rb, zb - c)]
    # skirt foot: outer chamfer 0.8, inner chamfer 0.6
    pts += [(R_SKIRT, Z_FOOT + 0.8), (R_SKIRT - 0.8, Z_FOOT),
            (R_IN + 0.6, Z_FOOT), (R_IN, Z_FOOT + 0.6)]
    # cavity: one bore up to an R6 fillet into the crown underside
    fr = 6.0
    pts += [(R_IN, Z_UNDER - fr),
            ("arc", _arc_mid((R_IN - fr, Z_UNDER - fr), fr, 0, 90), (R_IN - fr, Z_UNDER)),
            (0.0, Z_UNDER)]
    return pts


def _boss_face():
    """Pin boss + web section in the XZ (t-h) plane: a Ø58 boss hung from the
    crown on a drafted web, concave corners rounded R6."""
    circ = bd.Plane.XZ * bd.Circle(BOSS_R)
    # Plane.XZ local (x, y) -> world (X, Z)
    web = bd.Plane.XZ * bd.Polygon((-21.0, 8.0), (21.0, 8.0), (27.0, Z_UNDER + 3.0),
                                   (-27.0, Z_UNDER + 3.0), align=None)
    face = (circ + web).clean().faces()[0]
    concave = [v for v in face.vertices() if -1.0 < v.Z < Z_UNDER]
    try:
        face = bd.fillet(concave, radius=6.0)
    except Exception:
        pass
    return face


def _bosses():
    face = _boss_face()
    out = []
    for sgn in (1.0, -1.0):
        # Plane.XZ normal is -Y: extrude from y = sgn*19 outward to sgn*66
        f = bd.Pos(0, sgn * BOSS_Y0, 0) * face
        solid = bd.extrude(f, amount=66.0 - BOSS_Y0, dir=(0, sgn, 0))
        out.append(solid)
    return out


def _ribs():
    """Two stiffening ribs under the crown, parallel to the pin axis and outboard
    of the boss webs (clear of the rod small end), running wall to wall."""
    ribs = []
    w, z0, z1 = 6.0, 34.0, Z_UNDER + 2.0
    trim = bd.Pos(0, 0, z0 - 1) * bd.Cylinder(R_IN + 1.0, z1 - z0 + 2,
                                             align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    for t in (-42.0, 42.0):
        sec = bd.Plane.XZ * bd.Pos(t, (z0 + z1) / 2.0) * bd.Rectangle(w, z1 - z0)
        ribs.append(bd.extrude(bd.Pos(0, 70, 0) * sec, amount=140.0) & trim)
    return ribs


def _drain_holes():
    """Oil-return holes drilled through the roots of both oil-control grooves
    (they show through the rings' slots). The pin-boss sectors are left solid."""
    holes = []
    for _, zt, zb, root in GROOVES[3:5]:
        z = (zt + zb) / 2.0
        for i in range(16):
            a = 360.0 * (i + 0.5) / 16
            if abs(math.cos(math.radians(a))) < 0.5:          # boss sectors around +-Y
                continue
            u = (math.cos(math.radians(a)), math.sin(math.radians(a)))
            holes.append(geo.cyl_along((u[0] * (R_IN - 6), u[1] * (R_IN - 6), z),
                                       (u[0] * (root + 0.5), u[1] * (root + 0.5), z), 2.6))
    return holes


def _slab_t(t0, t1, z0, z1, y_half=200.0):
    """Box spanning t (= local X) in [t0, t1], z in [z0, z1], |y| <= y_half."""
    return bd.Pos((t0 + t1) / 2.0, 0.0, (z0 + z1) / 2.0) * bd.Box(t1 - t0, 2 * y_half, z1 - z0)


def _skirt_tube():
    """The slipper skirt below the shoulder, as its own clean prism: the skirt
    circle with both thrust sides cut to vertical flats (|t| = FLAT_T), walls
    FLAT_WALL thick behind the flats, every vertical corner rounded in the section,
    the foot edges broken. Fused under the ring belt in piston_body."""
    def clipped(r, half_t, rc):
        disc = bd.Circle(r)
        band = bd.Rectangle(2 * half_t, 3 * r)
        face = (disc & band).clean().faces()[0]
        corners = [v for v in face.vertices() if abs(abs(v.X) - half_t) < 1e-3]
        try:
            face = bd.fillet(corners, radius=rc)
        except Exception:
            pass
        return face
    outer = clipped(R_SKIRT, FLAT_T, 3.0)
    inner = clipped(R_IN, FLAT_T - FLAT_WALL, 2.0)
    section = (outer - inner).clean().faces()[0]
    tube = bd.extrude(bd.Pos(0, 0, Z_FOOT) * section, amount=Z_SHOULDER - Z_FOOT)
    foot = [e for e in tube.edges() if abs(e.position_at(0.5).Z - Z_FOOT) < 1e-3]
    tube, _ = C.safe_fillet(tube, foot, 0.8, min_r=0.4)
    return tube


def _notch_cutters():
    """Arched rod-relief notch through both flat walls at the foot."""
    zc = NOTCH_TOP - NOTCH_HW
    span = 2 * (FLAT_T + 2.0)
    arch = bd.Pos(0, 0, zc) * bd.Rot(0, 90, 0) * bd.Cylinder(NOTCH_HW, span)
    box = bd.Pos(0, 0, (zc + Z_FOOT - 10.0) / 2.0) * bd.Box(span, 2 * NOTCH_HW, zc - Z_FOOT + 10.0)
    notch = (arch + box).clean() - bd.Box(2 * (FLAT_T - FLAT_WALL - 1.0), 400, 400)
    return list(notch.solids())


def _in_notch(p):
    return (abs(p.X) > FLAT_T - FLAT_WALL - 0.05 and p.Z < NOTCH_TOP + 0.05
            and abs(p.Y) < NOTCH_HW + 0.05)


def pin_bore_tool():
    return bd.Rot(90, 0, 0) * bd.Cylinder(PIN_BORE_R, 200.0)


def _sharp(shape, edges, tol_deg=8.0):
    """Edges whose two faces meet at a real angle (tangent seams dropped: a
    fillet asked of a smooth seam fails the whole set)."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.ShapeAnalysis import ShapeAnalysis_Surface
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopoDS import TopoDS
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape
    from OCP.gp import gp_Pnt

    m = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape.wrapped, TopAbs_EDGE, TopAbs_FACE, m)
    out = []
    for e in edges:
        idx = m.FindIndex(e.wrapped)
        if idx == 0:
            continue
        faces = [TopoDS.Face_s(f) for f in m.FindFromIndex(idx)]
        if len(faces) != 2:
            continue
        p = e.position_at(0.5)
        ns = []
        for f in faces:
            uv = ShapeAnalysis_Surface(BRep_Tool.Surface_s(f)).ValueOfUV(gp_Pnt(p.X, p.Y, p.Z), 1e-6)
            props = BRepLProp_SLProps(BRepAdaptor_Surface(f), uv.X(), uv.Y(), 1, 1e-6)
            if not props.IsNormalDefined():
                break
            n = props.Normal()
            ns.append((n.X(), n.Y(), n.Z()))
        if len(ns) == 2 and abs(sum(a * b for a, b in zip(*ns))) < math.cos(math.radians(tol_deg)):
            out.append(e)
    return out


def piston_body():
    # revolve seam turned off the y = 0 plane (piston 1 is sectioned on it)
    shell = bd.Rot(0, 0, 7.0) * _revolve_rz(_piston_outline())
    keep = bd.Cylinder(R_IN + 1.5, 200.0)          # bosses end inside the wall, never in a groove
    bosses = [b & keep for b in _bosses()]
    body = shell.fuse(*bosses, *_ribs()).clean()
    # slipper skirt: the round skirt wall below the shoulder is replaced by the
    # flatted tube (thrust sides relieved to vertical flats, 4 mm walls)
    wall = (bd.Pos(0, 0, Z_FOOT - 5) * bd.Cylinder(90.0, Z_SHOULDER - Z_FOOT + 5,
                                                    align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
            - bd.Cylinder(R_IN, 400.0) - bosses)      # boss ends stay, embedded in the tube wall
    body = body.cut(wall).clean().fuse(_skirt_tube()).clean()
    # forging radii: every sharp edge inside the cavity (bosses, webs, ribs, crown)
    def inside(e):
        c = e.position_at(0.5)
        r = math.hypot(c.X, c.Y)
        at_tube_seam = (c.Z < Z_SHOULDER + 0.5 and r > R_IN - 0.5) or abs(c.Z - Z_SHOULDER) < 0.1
        return (r < R_IN + 0.5 and Z_FOOT + 2.0 < c.Z < Z_UNDER + 0.5
                and abs(abs(c.Y) - BOSS_Y0) > 0.5 and not at_tube_seam)
    edges = _sharp(body, [e for e in body.edges() if inside(e)])
    body, r = C.safe_fillet(body, edges, 2.0, min_r=1.0)
    if r is None:
        C._warn("pistons: underside forging fillets failed; left sharp")
    # soften the machined boss faces' outline (|y| = 19)
    rim = [e for e in body.edges()
           if abs(abs(e.position_at(0.5).Y) - BOSS_Y0) < 0.01 and abs(e.position_at(0.0).Y - e.position_at(1.0).Y) < 0.01]
    body, _ = C.safe_fillet(body, rim, 1.0, min_r=0.5)
    # slipper skirt: both thrust sides relieved to vertical flats from the foot to
    # a shoulder under the ring pack; the flats are real 4 mm walls, notched at the
    # foot for the rod's swing
    body = body.cut(pin_bore_tool(), *_drain_holes(), *_notch_cutters()).clean()
    notch = _sharp(body, [e for e in body.edges() if _in_notch(e.position_at(0.5))])
    body, r = C.safe_fillet(body, notch, 1.0, min_r=0.5)
    if r is None:
        C._warn("pistons: rod-notch edge radii failed; left sharp")
    ledge = [e for e in body.edges()
             if abs(e.position_at(0.5).Z - Z_SHOULDER) < 1e-3
             and math.hypot(e.position_at(0.5).X, e.position_at(0.5).Y) > R_SKIRT - 0.05]
    body, _ = C.safe_fillet(body, ledge, 0.8, min_r=0.4)
    lead = [e for e in body.edges() if abs(abs(e.position_at(0.5).Y) - BOSS_Y0) < 0.01
            and abs(math.hypot(e.position_at(0.5).X, e.position_at(0.5).Z) - PIN_BORE_R) < 0.01]
    body, _ = C.safe_chamfer(body, lead, 0.8, min_length=0.4)
    return body


# ---------------------------------------------------------------------------
# Rings (each a revolve with a real 0.4 mm end gap)
# ---------------------------------------------------------------------------
def _gap_deg(r):
    return math.degrees(0.4 / r)


def _ring(section, gap_at):
    r_out = max(p[0] for p in section if not (isinstance(p, tuple) and p[0] == "arc"))
    g = _gap_deg(r_out)
    ring = _revolve_rz(section, arc=360.0 - g)
    return bd.Rot(0, 0, gap_at + g / 2.0) * ring


def compression_ring(zt, zb, root, gap_at):
    zt, zb = zt - RING_SIDE, zb + RING_SIDE
    ri, ro = root + RING_BACK, R_RING_OD
    c = 0.25
    sec = [(ri, zb), (ro - c, zb), (ro, zb + c), (ro, zt - c), (ro - c, zt), (ri, zt)]
    return _ring(sec, gap_at)


def oil_ring(zt, zb, root, gap_at, slots=18):
    zt, zb = zt - RING_SIDE, zb + RING_SIDE
    ri, ro = root + RING_BACK, R_RING_OD
    zm = (zt + zb) / 2.0
    gw, gd = 1.6, 1.2          # central channel between the two scraping lands
    c = 0.2
    sec = [(ri, zb), (ro - c, zb), (ro, zb + c), (ro, zm - gw / 2), (ro - gd, zm - gw / 2),
           (ro - gd, zm + gw / 2), (ro, zm + gw / 2), (ro, zt - c), (ro - c, zt), (ri, zt)]
    ring = _ring(sec, gap_at)
    tools = []
    for i in range(slots):
        a = gap_at + 360.0 * (i + 0.5) / slots
        slot = bd.Box(ro - ri + 4, 9.0, 1.2)
        slot = bd.Rot(0, 0, a) * bd.Pos((ri + ro) / 2.0, 0, zm) * slot
        tools.append(slot)
    return ring.cut(*tools).clean()


def scraper_ring(zt, zb, root, gap_at):
    zt, zb = zt - RING_SIDE, zb + RING_SIDE
    ri, ro = root + RING_BACK, R_RING_OD
    # taper face: full diameter at the lower (scraping) edge, 0.8 mm in at the top
    sec = [(ri, zb), (ro - 0.15, zb), (ro, zb + 0.4), (ro - 0.8, zt), (ri, zt)]
    return _ring(sec, gap_at)


def rings():
    out = []
    gaps = (30.0, 150.0, 270.0, 90.0, 210.0, 330.0)   # staggered end gaps
    for i, (name, zt, zb, root) in enumerate(GROOVES):
        if name.startswith("c"):
            out.append(compression_ring(zt, zb, root, gaps[i]))
        elif name.startswith("o"):
            out.append(oil_ring(zt, zb, root, gaps[i]))
        else:
            out.append(scraper_ring(zt, zb, root, gaps[i]))
    return out


# ---------------------------------------------------------------------------
# Wrist pin + plugs (revolved about Y)
# ---------------------------------------------------------------------------
def wrist_pin():
    c = 0.8
    sec = [(PIN_ID_R + 0.6, -PIN_HALF), (PIN_R - c, -PIN_HALF), (PIN_R, -PIN_HALF + c),
           (PIN_R, PIN_HALF - c), (PIN_R - c, PIN_HALF), (PIN_ID_R + 0.6, PIN_HALF),
           (PIN_ID_R, PIN_HALF - 0.6), (PIN_ID_R, -PIN_HALF + 0.6)]
    return bd.Rot(-90, 0, 0) * _revolve_rz(sec)


def pin_plug(sign):
    """Aluminium domed plug: spigot in the pin bore, shoulder on the pin end,
    dome to just inside the bore wall."""
    stem_r, head_r = PIN_ID_R - 0.3, PIN_R - 0.8
    y0, y1, y2 = PIN_HALF - 9.0, PIN_HALF + 0.3, PIN_HALF + 2.2
    apex = PLUG_APEX
    # dome from (head_r, y2) to (0, apex): circular arc
    h = apex - y2
    R = (head_r ** 2 + h ** 2) / (2 * h)
    zc = apex - R
    rm = head_r * 0.55
    sec = [(0.0, y0 + 0.5), (stem_r - 0.5, y0), (stem_r, y0 + 0.5), (stem_r, y1),
           (head_r - 0.4, y1), (head_r, y1 + 0.4), (head_r, y2),
           ("arc", (rm, zc + math.sqrt(R * R - rm * rm)), (0.0, apex))]
    plug = bd.Rot(-90, 0, 0) * _revolve_rz(sec)       # local +Z -> +Y
    if sign < 0:
        plug = bd.Rot(0, 0, 180) * plug
    return plug


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
_PROTO = None


def prototypes():
    global _PROTO
    if _PROTO is None:
        parts = [("piston", piston_body(), P.CAST_ALU)]   # forged body: bright diffuse under the studio
        for i, r in enumerate(rings(), start=1):
            parts.append((f"ring_{i}", r, P.STEEL_DARK))
        parts.append(("wrist_pin", wrist_pin(), P.STEEL_MACHINED))
        parts.append(("pin_plug_a", pin_plug(-1), P.MACHINED_ALU))
        parts.append(("pin_plug_b", pin_plug(+1), P.MACHINED_ALU))
        _PROTO = parts
    return _PROTO


def piston_location(k: int) -> bd.Location:
    return geo.cyl_location(k) * bd.Location((0.0, 0.0, kin.piston_h(0.0, k)))


def _rear_half_removed(shape):
    """Museum section of piston 1: everything at y > 0 (the rear half) removed on
    the cylinder-row plane, over the piston's whole height. None when nothing is left."""
    keep = bd.Pos(0, -150.0, 0) * bd.Box(400.0, 300.0, 400.0)      # y in [-300, 0]
    bb = shape.bounding_box()
    if bb.min.Y >= -1e-6:
        return None
    if bb.max.Y <= 0.0:
        return shape
    res = shape & keep
    if not getattr(res, "_wrapped", None):
        raise RuntimeError("pistons: piston-1 section boolean failed")
    return res.clean()


_SECTIONED = None


def sectioned_prototypes():
    global _SECTIONED
    if _SECTIONED is None:
        out = []
        for name, shape, color in prototypes():
            cut = _rear_half_removed(shape)
            if cut is not None:
                out.append((name, cut, color))
        _SECTIONED = out
    return _SECTIONED


SKIN_T = 0.4                                # museum paint skin on each cut face (in the removed half)
_SKINS = None


def section_skins():
    """0.4 mm red skins on piston 1's y = 0 cut faces: the original part within
    y in [0, SKIN_T], lying just inside the removed half (never overlaps the part)."""
    global _SKINS
    if _SKINS is None:
        slab = bd.Pos(0, SKIN_T / 2.0, 0) * bd.Box(400.0, SKIN_T, 400.0)
        out = []
        for name, shape, _ in prototypes():
            if name.startswith("ring_"):
                continue            # ring cut faces are left bare steel for contrast (BUILDING.md)
            bb = shape.bounding_box()
            if not (bb.min.Y < 0.0 < bb.max.Y):
                continue
            skin = shape & slab
            if getattr(skin, "_wrapped", None) and skin.solids():
                out.append((f"section_skin_{name}", skin.clean(), P.SECTION_RED))
        _SKINS = out
    return _SKINS


def build():
    """Nine pistons; piston 1 is the museum section (rear half removed, so its
    `pin_plug_b` does not exist; red paint skins on its cut faces). All move
    with kin.pose_piston."""
    out = []
    for k in range(1, S.N_CYL + 1):
        loc = piston_location(k)
        protos = sectioned_prototypes() + section_skins() if k == 1 else prototypes()
        for name, shape, color in protos:
            out.append(P.style(loc * shape, f"piston{k}:{name}", color))
    return out
