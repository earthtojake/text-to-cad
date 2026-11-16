"""SHORT CIRCUIT, assembled: the playfield board on four legs, its furniture, the glass, the backbox.

    cad run src/machine.py

Models: `short_circuit` (powered off, flippers at rest), `short_circuit_lit` (powered on: the inserts,
the bumpers, the slings, the targets, the backbox's marquee and its display lit; a flipper up), each again
with the glass out (`short_circuit_open`, `short_circuit_lit_open`), and three close-up poses of the ball
(`short_circuit_detail_lane`, `short_circuit_detail_bumper`, and `short_circuit_cradle`, which `__main__`
leaves out). World frame: Z up, the player at -Y, the front legs' feet at y = 0; the playfield pitched
TILT_DEG.
"""
from __future__ import annotations

import math

import build123d as bd
from cad import model

import dotfont
import layout as L
import looks
import parts as X
import playfield as P

Z = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)


def table_to_world():
    """The playfield frame to the world: the board's front edge at y = 0, its underside there at Z_FRONT,
    pitched TILT_DEG about x."""
    return bd.Pos(0, 0, L.Z_FRONT) * bd.Rot(L.TILT_DEG, 0, 0) * bd.Pos(0, 0, L.BOARD_T)


def apron_cards():
    """Two cards in the apron's recesses: small black-and-gold boards, the name and the rules."""
    out = []
    top = 9.6                                     # 0.6 mm cards in the apron's 0.6 mm recesses, flush
    texts = {0: ("SHORT", "CIRCUIT"), 1: ("GND+VCC", "= SHORT")}
    for i, cx in enumerate(X.CARD_X):
        cy = (L.LOCKDOWN_D + L.APRON_Y[1]) / 2 + 0.5
        card = bd.Pos(cx, cy, top) * bd.Box(21.4, 10.4, 0.6, align=Z)
        out.append(X.tag(card, f"apron_card_{i + 1}", looks.soldermask()))
        pts = []
        for line, dy in zip(texts[i], (1.9, -1.9)):
            pts += [(x, y, 0.32) for x, y in dotfont.placed(line, 0.45, (cx, cy + dy))]
        out.append(X.tag(X.dots(pts, top + 0.6, 0.035), f"apron_card_{i + 1}_gold", looks.enig()))
    return out


def table(lit: bool, left: float, right: float, ball_at, with_glass: bool = True):
    """Everything in the playfield frame."""
    art = P.build_art()
    items = [X.playfield_board(), X.edge_plating(), *X.art_parts(art, lit)]
    items += [X.rail("left"), X.rail("right"), X.lockdown_bar(), X.apron(), *X.walls(), *X.lane_posts()]
    items += apron_cards()
    items += X.sling("left", lit) + X.sling("right", lit)
    for name in L.BUMPERS:
        items += X.bumper(name, lit)
    for name in L.TARGETS:
        items += X.target(name, lit)
    items += X.flipper("left", left) + X.flipper("right", right)
    items += X.plunger() + X.buttons(lit) + ([X.glass()] if with_glass else [])
    if ball_at is not None:
        items.append(X.ball(*ball_at))
    items += X.flipper_mech("left") + X.flipper_mech("right")
    items += X.underside_parts(lit)
    # the backbox, standing vertical: turned back by the playfield's pitch about the board's back edge, so it
    # stands level on a wedge that is thickest at its front
    upright = bd.Pos(0, L.BOARD_L, 0) * bd.Rot(-L.TILT_DEG, 0, 0) * bd.Pos(0, -L.BOARD_L, 0)
    for item in X.backbox_parts(lit):
        moved = upright * item
        moved.label, moved.material = item.label, item.material
        items.append(moved)
    y0 = L.BACKBOX_Y - 1.5
    rise = (L.BOARD_L - y0) * math.tan(math.radians(L.TILT_DEG))
    wedge = bd.extrude(bd.Plane.YZ * bd.Polygon((y0, 0.0), (L.BOARD_L, 0.0), (y0, rise), align=None),
                       amount=L.BOARD_W)
    items.append(X.tag(wedge, "backbox_wedge", looks.mjf_black()))
    return items


def cabinet(T):
    """The cabinet under the board, in the world: two smoked acrylic sides (the trapezoid: the board's
    pitch on top, the floor level), a front and a back panel, the aluminium floor plate, brass corner
    plates with their bolts."""
    t, ft = L.PANEL_T, L.FLOOR_T
    z0 = L.LEG_H
    back = (T * bd.Pos(0, L.BOARD_L, -L.BOARD_T)).position
    yb, zb = back.Y, back.Z
    zf = L.Z_FRONT
    tan = math.tan(math.radians(L.TILT_DEG))
    y0, y1 = -t, yb + t
    out = []
    zp = z0 + ft                                  # the panels stand on the floor plate
    side = bd.Polygon((y0, zp), (y1, zp), (y1, zb + t * tan), (y0, zf - t * tan), align=None)
    for name, x in (("left", -t), ("right", L.BOARD_W)):
        panel = bd.Pos(x, 0, 0) * bd.extrude(bd.Plane.YZ * side, amount=t)
        out.append(X.tag(panel, f"cabinet_side_{name}", looks.smoked_panel()))
    front = bd.Pos(L.BOARD_W / 2, -t / 2, zp) * bd.Box(L.BOARD_W, t, zf - zp - t * tan, align=Z)
    rear = bd.Pos(L.BOARD_W / 2, yb + t / 2, zp) * bd.Box(L.BOARD_W, t, zb - zp, align=Z)
    # the USB-C port's opening in the back panel, round the receptacle under the board's back edge
    usb = (T * bd.Pos(L.CENTER_X, L.BOARD_L, -L.BOARD_T - 1.6)).position
    port = bd.Pos(usb.X, yb + t / 2, usb.Z) * bd.Box(13.0, t + 2, 7.0)
    rear = rear - bd.fillet(port.edges().filter_by(bd.Axis.Y), 3.0)
    out.append(X.tag(front, "cabinet_front", looks.smoked_panel()))
    out.append(X.tag(rear, "cabinet_back", looks.smoked_panel()))
    floor = bd.Pos(L.BOARD_W / 2, (y0 + y1) / 2, z0) * bd.Box(L.BOARD_W + 2 * t, y1 - y0, ft, align=Z)
    floor = bd.fillet(floor.edges().filter_by(bd.Axis.Z), 1.5)
    out.append(X.tag(floor, "cabinet_floor", looks.anodised_black()))
    # small brass corner brackets: a 1.5 mm angle, 14 x 14 mm, one countersunk M2 a face, flush with the leg
    for cx, cy, sx, sy in ((-t, y0, 1, 1), (L.BOARD_W + t, y0, -1, 1), (-t, y1, 1, -1), (L.BOARD_W + t, y1, -1, -1)):
        a = bd.Pos(cx + sx * 7.0, cy - sy * 0.75, z0) * bd.Box(14.0, 1.5, 14.0, align=Z)
        b = bd.Pos(cx - sx * 0.75, cy + sy * 7.0, z0) * bd.Box(1.5, 14.0, 14.0, align=Z)
        out.append(X.tag(a + b, "corner_bracket", looks.brass()))
        for (px, py, d) in ((cx + sx * 8.0, cy - sy * 1.5, (0, -sy, 0)), (cx - sx * 1.5, cy + sy * 8.0, (-sx, 0, 0))):
            screw = bd.Solid.make_cone(1.9, 1.0, 0.1, bd.Plane(origin=(px, py, z0 + 8.0), z_dir=d))
            out.append(X.tag(screw, "corner_screw", looks.brass()))
    return out


def legs(T):
    """Four legs under the floor plate's corners: tapered square aluminium (LEG at the top, 8 mm at the
    foot), black anodised, their edges chamfered; a brass collar at the top; a leveller (an M5 thread, a nut,
    a rubber foot) under each."""
    out = []
    t = L.PANEL_T
    back = (T * bd.Pos(0, L.BOARD_L, 0)).position
    for corner, (x, y) in (("lf", (-t + L.LEG_INSET, -t + L.LEG_INSET)),
                           ("rf", (L.BOARD_W + t - L.LEG_INSET, -t + L.LEG_INSET)),
                           ("lb", (-t + L.LEG_INSET, back.Y + t - L.LEG_INSET)),
                           ("rb", (L.BOARD_W + t - L.LEG_INSET, back.Y + t - L.LEG_INSET))):
        top = L.LEG_H
        tube = bd.Pos(x, y, 10.0) * bd.Box(L.LEG, L.LEG, top - 3.0 - 10.0, align=Z)
        tube = bd.chamfer(tube.edges().filter_by(bd.Axis.Z), 0.8)
        out.append(X.tag(tube, f"leg_{corner}", looks.anodised_black()))
        ring = bd.Box(L.LEG + 1.0, L.LEG + 1.0, 3.0, align=Z)
        ring = bd.chamfer(ring.edges().filter_by(bd.Axis.Z), 0.5)
        out.append(X.tag(bd.Pos(x, y, top - 3.0) * ring, f"leg_{corner}_collar", looks.brass()))
        nut = bd.Pos(x, y, 6.0) * bd.extrude(bd.RegularPolygon(8.0 / math.sqrt(3), 6), 4.0)
        nut = bd.chamfer(nut.edges().group_by(bd.Axis.Z)[-1], 0.5)
        thread = bd.Pos(x, y, 2.5) * bd.Cylinder(2.5, 5.0, align=Z)
        nut = nut - thread
        foot = bd.Pos(x, y, 0) * bd.Cylinder(5.6, 2.5, align=Z)
        foot = bd.fillet(foot.edges().group_by(bd.Axis.Z)[0], 0.8)
        out += [X.tag(nut, f"leg_{corner}_nut", looks.steel()), X.tag(thread, f"leg_{corner}_leveller", looks.steel()),
                X.tag(foot, f"leg_{corner}_foot", looks.rubber_black())]
    return out


def build(lit: bool, left=None, right=None, ball_at=(L.SHOOTER_X, L.BALL_READY_Y), label="short_circuit",
          with_glass: bool = True):
    T = table_to_world()
    placed = []
    for item in table(lit, left, right, ball_at, with_glass):
        moved = T * item
        moved.label, moved.material = item.label, item.material
        placed.append(moved)
    return bd.Compound(children=placed + cabinet(T) + legs(T), label=label)


@model
def short_circuit():
    """Powered off, flippers at rest, the ball waiting on the plunger."""
    return build(False)


@model
def short_circuit_lit():
    """Powered on: every light lit, the right flipper up, the ball on its way up the field."""
    return build(True, right=L.FLIPPER_UP, ball_at=(L.CENTER_X, 78.0), label="short_circuit_lit")


@model
def short_circuit_open():
    """Powered off, the glass out (for a clear look at the playfield)."""
    return build(False, label="short_circuit_open", with_glass=False)


@model
def short_circuit_lit_open():
    """Powered on, the glass out."""
    return build(True, right=L.FLIPPER_UP, ball_at=(L.CENTER_X, 78.0), label="short_circuit_lit_open",
                 with_glass=False)


@model
def short_circuit_cradle():
    """For the close-ups: the left flipper held up, the ball cradled on it (8 mm along the bat), lit."""
    return build(True, left=L.FLIPPER_UP, ball_at=(26.98, 53.46), label="short_circuit_cradle", with_glass=False)


def _bumper_touch(name="C3", angle_deg=-115.0):
    x, y = L.BUMPERS[name]
    r = L.BUMPER_POST_R - 0.6 + 2 * 0.8 + L.BALL_R
    return (x + r * math.cos(math.radians(angle_deg)), y + r * math.sin(math.radians(angle_deg)))


@model
def short_circuit_detail_lane():
    """For the close-ups: the ball rolling over the N lane's gold comb, the left flipper up, lit."""
    return build(True, left=L.FLIPPER_UP, ball_at=(L.TOP_LANES["N"], L.TOP_LANE_Y[0] + 7.6),
                 label="short_circuit_detail_lane", with_glass=False)


@model
def short_circuit_detail_bumper():
    """For the close-ups: the ball against C3's ring, standing on its gold comb, powered off."""
    return build(False, ball_at=_bumper_touch(), label="short_circuit_detail_bumper", with_glass=False)


if __name__ == "__main__":
    short_circuit()
    short_circuit_lit()
    short_circuit_open()
    short_circuit_lit_open()
    short_circuit_detail_lane()
    short_circuit_detail_bumper()
    short_circuit_cradle()
