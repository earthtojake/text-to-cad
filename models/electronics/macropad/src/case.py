"""Nine's FDM-printed case, built around the board: a tray (heat-set insert bosses under the board's
mounting holes, the USB-C opening at the receptacle, pin holes under BOOT and RESET, recesses for
rubber feet) and an integrated switch plate (1.5 mm under the switch tops, a 14.1 mm cut-out at each
key the board places, the encoder's body window, spacer bosses down to the board at each hole).
Simple keycaps (one shape; `dish` is the legend-free top's depth, 0 for a flat top that prints face
down) and the encoder's knob.

Everything is read from the board file through board_geometry.read(): move a key, a hole, the encoder
or the USB receptacle on the board, run this script again, and the case follows.

    cad run src/case.py

Frame: the board's STEP (x, -y of the board file; z = 0 at the board's bottom face).
"""
import build123d as bd
from cad import model

from lib import board_geometry

THICK = board_geometry.THICK
PLATE_T = 1.5              # MX plate thickness, under the switch tops
PLATE_TOP = THICK + 5.0    # MX: the plate's top is 5.0 mm above the board's top
PLATE_BOT = PLATE_TOP - PLATE_T
GAP = 0.4                  # board edge to the tray's inner wall
WALL = 2.4
FLOOR_T = 2.0
FLOOR_TOP = -5.4           # 5.4 mm under the board: the USB-C receptacle (3.3 mm) and the plug's overmold
CUT = 14.1                 # MX plate cut-out 14.0 mm, +0.1 for FDM
INSERT_D, INSERT_DEPTH = 3.2, 4.0   # M2 x 3 mm heat-set insert (e.g. Ruthex M2 x 3.0, OD 3.6, hole 3.2)
SCREW_CLEAR = 2.4          # M2 clearance
BOSS_D = 6.0               # tray bosses (insert walls 1.4 mm)
SPACER_D = 4.6             # plate spacers between four switches (the gap there is 5.15 mm)
USB_W, USB_BOTTOM = 13.0, -5.1     # plug overmold opening: 12.4 mm cables pass, down to z -5.1
FOOT_D, FOOT_DEPTH = 8.4, 0.8      # 8 mm bump-on feet
FIT = 0.3


def _face(points):
    return bd.make_face(bd.Polyline(*points, close=True))


def _prism(face, z0, z1):
    return bd.Pos(0, 0, z0) * bd.extrude(face, z1 - z0)


def _cyl(xy, d, z0, z1):
    return bd.Pos(xy[0], xy[1], z0) * bd.Cylinder(d / 2, z1 - z0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))


def _rounded(g, grow):
    x0, y0, x1, y1 = g["box"]
    return bd.Pos((x0 + x1) / 2, (y0 + y1) / 2) * bd.RectangleRounded(x1 - x0 + 2 * grow, y1 - y0 + 2 * grow,
                                                                      g["corner"] + grow)


def outlines(g):
    """The board's outline (a rounded rectangle on the board file), and it grown for the tray."""
    return _rounded(g, 0), _rounded(g, GAP), _rounded(g, GAP + WALL)


def tray_body(g):
    _, inner, outer = outlines(g)
    body = _prism(outer, FLOOR_TOP - FLOOR_T, PLATE_BOT) - _prism(inner, FLOOR_TOP, PLATE_BOT + 1)
    for ref, (xy, _) in g["holes"].items():
        body += _cyl(xy, BOSS_D, FLOOR_TOP - 0.01, 0.0)
        body -= _cyl(xy, INSERT_D, -INSERT_DEPTH, 0.01)
        body -= _cyl(xy, 1.8, FLOOR_TOP - 0.6, -INSERT_DEPTH + 0.01)   # the screw's tip; 1.4 mm floor stays
    # the USB-C opening: a slot down through the back wall (+y), its bottom corners rounded
    x0, y_face = g["usb"]["x"], g["usb"]["face_y"]
    r, y0, y1 = 2.0, y_face - 1.0, y_face + GAP + WALL + 1.0
    top = PLATE_BOT + 1.0

    def box(xa, xb, za, zb):
        return bd.Pos((xa + xb) / 2, (y0 + y1) / 2, (za + zb) / 2) * bd.Box(xb - xa, y1 - y0, zb - za)
    cutter = box(x0 - USB_W / 2, x0 + USB_W / 2, USB_BOTTOM + r, top)
    cutter += box(x0 - USB_W / 2 + r, x0 + USB_W / 2 - r, USB_BOTTOM, USB_BOTTOM + r + 0.01)
    for sx in (-1, 1):
        cutter += bd.Pos(x0 + sx * (USB_W / 2 - r), (y0 + y1) / 2, USB_BOTTOM + r) * bd.Rot(90, 0, 0) * bd.Cylinder(
            r, y1 - y0)
    body -= cutter
    # BOOT and RESET: a paperclip through the floor
    for xy in g["buttons"].values():
        body -= _cyl(xy, 2.5, FLOOR_TOP - FLOOR_T - 1, FLOOR_TOP + 0.5)
    # (no foot recesses: their 0.8 mm ceilings were the tray's only overhangs; stick-on feet go on the flat floor)
    return body


def plate_body(g):
    _, _, outer = outlines(g)
    body = _prism(outer, PLATE_BOT, PLATE_TOP)
    for xy in g["keys"].values():
        body -= bd.Pos(xy[0], xy[1], PLATE_BOT - 1) * bd.Box(CUT, CUT, PLATE_T + 2, align=(
            bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    sx, sy = g["encoder"]["shaft"]
    bx, by = g["encoder"]["body"]
    body -= bd.Pos(sx, sy, PLATE_BOT - 1) * bd.Box(bx + 2 * FIT, by + 2 * FIT, PLATE_T + 2,
                                                   align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    _, inner, _ = outlines(g)
    room = _prism(bd.offset(inner, -FIT), THICK - 1, PLATE_BOT + 1)   # spacers stay inside the tray's walls
    for ref, (xy, _) in g["holes"].items():
        # a spacer down to the board between the keys; at the corners the tray's wall carries the plate,
        # and a spacer there would thin to 0.55 mm against the wall (the printing check found it)
        if ref in ("H1", "H2", "H3", "H4"):
            body += _cyl(xy, SPACER_D, THICK, PLATE_BOT + 0.01) & room
        body -= _cyl(xy, SCREW_CLEAR, THICK - 0.1, PLATE_TOP + 0.1)
    # the name, cut through the strip beside the knob as a stencil (N, I and E have no counters to
    # float): the board's copper shows through, and the face-down print has no ceiling to bridge
    text = bd.Pos(98.0, -61.0, PLATE_BOT - 1.0) * bd.extrude(bd.Text("NINE", 7.0, font_style=bd.FontStyle.BOLD), PLATE_T + 2)
    body -= text
    return body


def keycap_body(dish=0.0, width=18.0, top=12.6, height=7.6, wall=1.3, roof=1.2):
    """One legend-free keycap. `dish` > 0 scoops the top (then print it on its side or with supports)."""
    shell = bd.loft([bd.RectangleRounded(width, width, 1.5), bd.Pos(0, 0, height) * bd.RectangleRounded(top, top, 2.0)])
    inner = bd.loft([bd.Pos(0, 0, -0.01) * bd.RectangleRounded(width - 2 * wall, width - 2 * wall, 0.6),
                     bd.Pos(0, 0, height - roof) * bd.RectangleRounded(top - 2 * wall, top - 2 * wall, 0.8)])
    cap = shell - inner
    if dish > 0:
        cap -= bd.Pos(0, 0, height + 20 - dish) * bd.Rot(0, 90, 0) * bd.Cylinder(20, width + 2)
    stem = bd.Pos(0, 0, 0.5) * bd.Cylinder(2.75, height - roof - 0.5 + 0.01, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    for w, h in ((4.2, 1.35), (1.35, 4.2)):   # MX cross 4.0 x 1.17, + FDM allowance
        stem -= bd.Pos(0, 0, 0.4) * bd.Box(w, h, 4.1, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return cap + stem


KEYCAP_Z = THICK + 12.3          # the skirt's bottom, 0.7 mm above the switch housing's top


def knob_body(od=19.0, height=14.0, bore=6.1, flat=4.6, ridges=24):
    """The encoder's knob: D-bore for the EC11's 6 mm shaft, a recess over its bushing, a grip."""
    k = bd.Cylinder(od / 2, height, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    for i in range(ridges):
        # flutes open at the bottom, so printed top-down they end in no ceiling
        k -= bd.Rot(0, 0, i * 360 / ridges) * bd.Pos(od / 2 + 0.15, 0, -0.1) * bd.Cylinder(
            0.6, height + 0.2, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    # over the bushing and the round foot of the shaft (its D-flat starts 1.5 mm above the bushing)
    k -= bd.Cylinder(4.0, 5.8, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    d = bd.Cylinder(bore / 2, height - 1.2, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    d -= bd.Pos(flat - bore / 2, -5, 0) * bd.Box(5, 10, height, align=(bd.Align.MIN, bd.Align.MIN, bd.Align.MIN))
    k -= d
    k -= bd.Pos(0, od / 2 - 2.2, height) * bd.Box(1.0, 3.0, 2.0)   # a pointer groove, 1 mm deep, open on the top
    return k


KNOB_Z = THICK + 7.4             # 0.9 mm above the encoder body, 2.4 mm above the plate


@model
def tray():
    b = tray_body(board_geometry.read())
    b.label, b.color = "tray", "#3e4a59"
    return b


@model
def plate():
    b = plate_body(board_geometry.read())
    b.label, b.color = "plate", "#e8e4dc"
    return b


@model
def keycap():
    c = keycap_body()
    c.label, c.color = "keycap", "#f2efe9"
    return c


@model
def knob():
    k = knob_body()
    k.label, k.color = "knob", "#c8553d"
    return k


# print orientation: each part as it lies on the bed (the plate, keycap and knob face down)
@model
def tray_print():
    p = tray().shape
    p.label = "tray"
    return bd.Pos(0, 0, -(FLOOR_TOP - FLOOR_T)) * p


@model
def plate_print():
    p = bd.Rot(180, 0, 0) * plate().shape
    p = bd.Pos(0, 0, -p.bounding_box().min.Z) * p
    p.label = "plate"
    return p


@model
def keycap_print():
    p = bd.Rot(180, 0, 0) * keycap().shape
    p = bd.Pos(0, 0, -p.bounding_box().min.Z) * p
    p.label = "keycap"
    return p


@model
def knob_print():
    p = bd.Rot(180, 0, 0) * knob().shape
    p = bd.Pos(0, 0, -p.bounding_box().min.Z) * p
    p.label = "knob"
    return p


if __name__ == "__main__":
    for m in (tray, plate, keycap, knob, tray_print, plate_print, keycap_print, knob_print):
        m()
