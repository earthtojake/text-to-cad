"""Orbit's printed parts and its assembly, designed around the board's real geometry.

Every dimension that comes from the board is read from it, never retyped: the outline (its arc's circle and
its flat), the mounting holes and every LED from orbit.kicad_pcb (kicad_pcb.read), and every part's 3D extent
from the board's own STEP export, converted once to XBF/orbit.xbf (README: "Rebuild").

- baffle: black PLA, on the board's face: a cell over each of the 60 minute LEDs (a wedge between walls of
  constant thickness) and the 12 hour LEDs (a round light pipe), so each LED lights its own cell only; a
  window over the ambient light sensor; pockets underneath for every part outside a cell; M3 pilot holes on
  the board's mounting holes; four peg holes for the diffuser.
- diffuser: a 1.2 mm translucent disc (natural PETG) on the baffle, located by four pegs.
- stand: black PLA, holding the stack by its rim, tilted back 12 degrees, a pocket for the USB-C plug under
  the board's flat and a cable channel under the base to the back.
- orbit: the assembly, with an explode animation (diffuser forward, baffle forward, the board out of the stand).

Frame: the board's local frame is its outline's centre, x right, y up (to 12 o'clock), z out of the face,
the board's back at z = 0 (the STEP's own z). The assembly stands the clock up in world space, face to -Y.
"""
from __future__ import annotations

import math
from pathlib import Path

import build123d as bd
from bd_materials import plastics
from cad import kicad_pcb, model, xbf
from cad.build123d import animation

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
BOARD_FILE = PROJECT / "orbit.kicad_pcb"
BOARD_XBF = PROJECT / "XBF" / "orbit.xbf"

# The printed parts' own dimensions (design choices, not the board's)
BAFFLE_GAP = 0.05        # the baffle sits on the board's face (a hair off it, so contact is not overlap)
BAFFLE_H = 8.0           # cell depth: LED to diffuser
WALL = 1.6               # cell walls (FDM: >= 1.6 mm unsupported, skills/cad/references/manufacturing-printing.md)
MINUTE_CELL = (45.4, 54.6)  # the minute cells' radial extent (the LEDs at 50 mm, their capacitors at 47.6 mm)
HOUR_CELL_R = 3.8        # the hour light pipes' radius
SENSOR_R = 1.6           # the light sensor's window
POCKET_MARGIN, POCKET_CLEAR = 0.4, 0.4
OUTLINE_INSET = 0.5      # the printed parts stop short of the board's edge
DIFFUSER_T = 1.2
PEG_D, PEG_HOLE_D, PEG_L, PEG_R, PEG_ANGLES = 3.0, 3.25, 2.2, 42.0, (15.0, 105.0, 195.0, 285.0)
PILOT_D, PILOT_DEPTH = 2.6, 6.0   # M3 x 8 self-tapping screws from the back
TILT = 12.0              # degrees back from vertical
SLOT_CLEAR = 0.3         # the stand's slot round the stack
LIP_R = 55.6             # the front lip covers the rim down to this radius (the minute cells end at 54.6)
BACK_WALL_R, BACK_WALL_T = 47.0, 6.0
BASE = (112.0, 66.0, 34.0)   # the plinth: width, depth, height (the plug and its cable bend need ~30 mm)
PLUG = (13.4, 7.6, 30.0)     # USB-C overmold + clearance: width, thickness, length below the flat


# ----------------------------------------------------------------------------------- the board, read back

def circle_through(a, b, c):
    (x1, y1), (x2, y2), (x3, y3) = a, b, c
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    ux = ((x1 ** 2 + y1 ** 2) * (y2 - y3) + (x2 ** 2 + y2 ** 2) * (y3 - y1) + (x3 ** 2 + y3 ** 2) * (y1 - y2)) / d
    uy = ((x1 ** 2 + y1 ** 2) * (x3 - x2) + (x2 ** 2 + y2 ** 2) * (x1 - x3) + (x3 ** 2 + y3 ** 2) * (x2 - x1)) / d
    return ux, uy, math.dist((ux, uy), a)


class Board:
    """The saved board in its local frame (outline centre, y up)."""

    def __init__(self):
        b = kicad_pcb.read(str(BOARD_FILE))
        arc = next(s for s in b.shapes if s.layer == "Edge.Cuts" and s.shape == "arc")
        flat = next(s for s in b.shapes if s.layer == "Edge.Cuts" and s.shape == "line")
        pts = arc.points
        self.cx, self.cy, self.radius = circle_through(pts[0], pts[len(pts) // 2], pts[-1])
        self.flat_y = -(flat.points[0][1] - self.cy)
        self.holes = [(self.local(h.at), h.diameter) for h in b.holes if h.diameter >= 3.0]
        self.leds = []
        for part in b.parts:
            if part.ref.startswith("D"):
                x, y = self.local(part.at)
                self.leds.append((part.ref, (x, y), math.hypot(x, y), math.degrees(math.atan2(x, y)) % 360))
        self.minute = sorted((l for l in self.leds if l[2] > 44.0), key=lambda l: l[3])
        self.hour = sorted((l for l in self.leds if l[2] <= 44.0), key=lambda l: l[3])
        self.sensor = self.local(b.part("U5").at)
        self.usb = self.local(b.part("J1").at)
        self.parts = {p.ref: p for p in b.parts}

    def local(self, p):
        return (p[0] - self.cx, -(p[1] - self.cy))

    def step_to_local(self):
        """The board STEP's frame (KiCad x, -y, z) to this one."""
        return bd.Pos(-self.cx, self.cy, 0)


def prism(face, z0, z1):
    """A face (on z = 0) extruded from z0 to z1, whichever way its points wind."""
    return bd.Pos(0, 0, z0) * bd.extrude(face, amount=z1 - z0, dir=(0, 0, 1))


def outline_face(g: Board, inset: float):
    """The board's outline (a circle cut by its flat), shrunk by `inset`, as a face on z = 0."""
    disc = bd.Circle(g.radius - inset)
    keep = bd.Pos(0, g.flat_y + inset + 200, 0) * bd.Rectangle(400, 400)
    return disc & keep


def placed_children(parts):
    """Each part of the board's tree with the tree's own placement applied (a child's box is its parent's
    frame, so a moved tree's children must be placed before they are measured)."""
    for child in parts.children:
        yield child.located(parts.location * child.location)


def board_parts(g: Board):
    """The board's STEP, as built: the PCB and each part, in the local frame."""
    tree = xbf.read(str(BOARD_XBF))
    return g.step_to_local() * tree


# ----------------------------------------------------------------------------------- the baffle

def minute_cell(r_in, r_out, deg, pitch_deg):
    """A wedge round an LED at `deg` (clockwise from 12) between two walls of WALL thickness, as a face."""
    def at(r, side):
        half = pitch_deg / 2 - math.degrees(WALL / 2 / r)
        a = math.radians(deg + side * half)
        return (r * math.sin(a), r * math.cos(a))
    pts = [at(r_in, -1), at(r_out, -1), at(r_out, 1), at(r_in, 1)]
    return bd.Polygon(*pts, align=None)


def baffle_body(g: Board, parts):
    z0 = 1.6 + BAFFLE_GAP
    body = prism(outline_face(g, OUTLINE_INSET), 0, BAFFLE_H)
    cells = []
    pitch = 360.0 / len(g.minute)
    for ref, (x, y), r, deg in g.minute:
        cells.append(prism(minute_cell(*MINUTE_CELL, deg, pitch), 0, BAFFLE_H))
    for ref, (x, y), r, deg in g.hour:
        cells.append(bd.Pos(x, y, 0) * bd.Cylinder(HOUR_CELL_R, BAFFLE_H, align=(bd.Align.CENTER,) * 2 + (bd.Align.MIN,)))
    cells.append(bd.Pos(*g.sensor, 0) * bd.Cylinder(SENSOR_R, BAFFLE_H, align=(bd.Align.CENTER,) * 2 + (bd.Align.MIN,)))
    body = body - bd.Compound(children=cells)
    # Pockets underneath for every part that stands above the board's face outside a cell
    pockets = []
    for part in placed_children(parts):
        if part.label in ("orbit", "PCB") or not part.label:
            continue
        bb = part.bounding_box()
        top = bb.max.Z - 1.6
        if top < 0.02:
            continue
        cx, cy = (bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2
        if part.label.startswith("D") or (part.label.startswith("C") and len(part.label) == 4):
            continue   # the ring's LEDs and capacitors stand in their cells
        w, h = bb.size.X + 2 * POCKET_MARGIN, bb.size.Y + 2 * POCKET_MARGIN
        pockets.append(bd.Pos(cx, cy, -BAFFLE_GAP) * bd.Box(w, h, top + POCKET_CLEAR,
                                                           align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    if pockets:
        body = body - bd.Compound(children=pockets)
    holes = [bd.Pos(x, y, 0) * bd.Cylinder(PILOT_D / 2, PILOT_DEPTH, align=(bd.Align.CENTER,) * 2 + (bd.Align.MIN,))
             for (x, y), d in g.holes]
    for deg in PEG_ANGLES:
        a = math.radians(deg)
        holes.append(bd.Pos(PEG_R * math.sin(a), PEG_R * math.cos(a), BAFFLE_H - PEG_L - 0.3) *
                     bd.Cylinder(PEG_HOLE_D / 2, PEG_L + 0.3, align=(bd.Align.CENTER,) * 2 + (bd.Align.MIN,)))
    body = body - bd.Compound(children=holes)
    return bd.Pos(0, 0, z0) * body


def diffuser_body(g: Board):
    z0 = 1.6 + BAFFLE_GAP + BAFFLE_H
    disc = prism(outline_face(g, OUTLINE_INSET), 0, DIFFUSER_T)
    top = disc.edges().group_by(bd.Axis.Z)[-1]
    disc = bd.chamfer(top, 0.5)
    pegs = []
    for deg in PEG_ANGLES:
        a = math.radians(deg)
        pegs.append(bd.Pos(PEG_R * math.sin(a), PEG_R * math.cos(a), 0) *
                    bd.Cylinder(PEG_D / 2, PEG_L, align=(bd.Align.CENTER,) * 2 + (bd.Align.MAX,)))
    return bd.Pos(0, 0, z0) * (disc + bd.Compound(children=pegs))


# ----------------------------------------------------------------------------------- the stand

def stack_front(g):
    return 1.6 + BAFFLE_GAP + BAFFLE_H + DIFFUSER_T


def placement(g: Board):
    """Local (board) frame to world: face to -Y, 12 o'clock up, tilted back TILT, the flat's middle (its back
    face's plane) on the plinth's top at x = 0."""
    stand_up = bd.Rot(-TILT, 0, 0) * bd.Rot(90, 0, 0)
    low = stand_up * bd.Pos(0, g.flat_y, 0)
    p = low.position
    return bd.Pos(-p.X, -p.Y + 4.0, BASE[2] + 3.0 - p.Z) * stand_up


def sector(r_in, r_out, a0, a1, z0, z1):
    """An annular sector in the local frame (angles clockwise from 12 o'clock), z0..z1."""
    n = 24
    pts = [(r_out * math.sin(math.radians(a0 + (a1 - a0) * k / n)), r_out * math.cos(math.radians(a0 + (a1 - a0) * k / n)))
           for k in range(n + 1)]
    pts += [(r_in * math.sin(math.radians(a1 - (a1 - a0) * k / n)), r_in * math.cos(math.radians(a1 - (a1 - a0) * k / n)))
            for k in range(n + 1)]
    return prism(bd.Polygon(*pts, align=None), z0, z1)


def stand_body(g: Board, parts):
    T = placement(g)
    front = stack_front(g)
    w, d, h = BASE
    # the plinth, a rounded slab
    base = bd.Box(w, d, h, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    base = bd.fillet(base.edges().filter_by(bd.Axis.Z), 10.0)
    base = bd.fillet(base.edges().group_by(bd.Axis.Z)[-1], 2.0)
    # the cradle round the rim, in the board's frame: a saddle under the stack, from behind the board to in
    # front of the diffuser, its top the rim's circle grown by 4.5 mm; the slot, the lip and the back wall cut
    # from it below
    # (a straight-sided block: an arc-sided one hangs its sides over the plinth, which the printing check flags)
    saddle = bd.Pos(0, g.flat_y - 6.0, 0) * bd.Rectangle(84.0, 32.0)
    cradle = prism(saddle, -SLOT_CLEAR - BACK_WALL_T, front + SLOT_CLEAR + 3.0)
    r_rim = g.radius + SLOT_CLEAR
    body = base + T * cradle
    # the slot the stack drops into: the rim's circle, from the board's back to the diffuser's face
    slot = bd.Pos(0, 0, -SLOT_CLEAR) * bd.Cylinder(r_rim, front + 2 * SLOT_CLEAR,
                                                   align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    slot += bd.Pos(0, 0, -SLOT_CLEAR) * bd.Box(2 * r_rim, 200, front + 2 * SLOT_CLEAR,
                                               align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    above_lip = bd.Cylinder(LIP_R, 60, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    above_lip += bd.Pos(0, 0, 0) * bd.Box(2 * LIP_R, 200, 60, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    behind = bd.Pos(0, 0, -60) * bd.Cylinder(BACK_WALL_R, 60, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    behind += bd.Pos(0, 0, -60) * bd.Box(2 * BACK_WALL_R, 200, 60, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    cuts = [slot, above_lip, behind]
    # pockets behind the board for its back-side parts in the cradle (the receptacle, the polyfuse ...)
    for part in placed_children(parts):
        if not part.label or part.label == "PCB":
            continue
        bb = part.bounding_box()
        if bb.min.Z > -0.02 or bb.max.Y > -BACK_WALL_R + 2:
            continue
        cuts.append(bd.Pos((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, bb.min.Z - POCKET_CLEAR) *
                    bd.Box(bb.size.X + 2 * POCKET_MARGIN, bb.size.Y + 2 * POCKET_MARGIN,
                           -bb.min.Z + POCKET_CLEAR + 0.1, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)))
    # the USB-C plug, straight down from the receptacle under the flat
    ux = g.usb[0]
    cuts.append(bd.Pos(ux, g.flat_y, -1.6) * bd.Box(PLUG[0], PLUG[2] * 2, PLUG[1],
                                                    align=(bd.Align.CENTER, bd.Align.MAX, bd.Align.CENTER)))
    body = body - T * bd.Compound(children=cuts)
    # the cable's channel under the plinth, from the plug's pocket to the back
    plug_end = (T * bd.Pos(ux, g.flat_y - PLUG[2], -1.6)).position
    # (a 45-degree roof, so the channel prints without supports)
    def tunnel(width, height, length, at, along_y=True):
        w = width / 2
        prof = bd.Polygon((-w, 0), (w, 0), (w, height), (0, height + w), (-w, height), align=None)
        solid = bd.extrude(bd.Plane.XZ * prof, amount=length, dir=(0, 1, 0))
        return bd.Pos(*at) * solid
    channel = tunnel(6.0, 4.0, d, (plug_end.X, plug_end.Y - 4.0, 0))
    channel += tunnel(PLUG[0], 4.0, PLUG[1] + 6.0, (plug_end.X, plug_end.Y - (PLUG[1] + 6.0) / 2, 0))
    body = body - channel
    # nothing below the plinth's floor
    body = body & bd.Box(400, 400, 200, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    return body


# ----------------------------------------------------------------------------------- the models

def labelled(shape, label, material, color):
    shape.label = label
    shape.material = material
    shape.color = color
    return shape


@model
def baffle():
    g = Board()
    return labelled(baffle_body(g, board_parts(g)), "baffle", plastics.pla(), "#1b1c1f")


@model
def diffuser():
    g = Board()
    d = labelled(diffuser_body(g), "diffuser", plastics.petg(), "#f2f0ea")
    d.material.pbr = d.material.pbr.override(transmission=0.6, roughness=0.55)
    d.color = bd.Color(0.96, 0.95, 0.93, 0.8)
    return d


@model
def stand():
    g = Board()
    return labelled(stand_body(g, board_parts(g)), "stand", plastics.pla(), "#26272b")


# ----------------------------------------------------------------------------------- print orientations

def on_plate(shape):
    """Turned face down (180 degrees about X) and set on z = 0: how the diffuser and the baffle print."""
    turned = bd.Rot(180, 0, 0) * shape
    return bd.Pos(0, 0, -turned.bounding_box().min.Z) * turned


@model
def diffuser_print():
    """The diffuser as it prints: its face on the plate, its pegs up."""
    d = on_plate(diffuser().shape)
    d.label = "diffuser"
    return d


@model
def front_print():
    """The diffuser and the baffle as ONE two-material print (a printer with two filaments): the natural PETG
    face on the plate, the black baffle printed onto it, the pegs in their holes."""
    g = Board()
    stack = bd.Compound(children=[diffuser().shape, baffle().shape])
    turned = on_plate(stack)
    d, b = turned.children
    d.label, b.label = "diffuser", "baffle"
    return bd.Compound(children=[d, b], label="front")


@model
def pcb():
    g = Board()
    tree = board_parts(g)
    tree.label = "board"
    return tree


@model
def orbit():
    g = Board()
    T = placement(g)
    board = pcb().shape
    parts = [stand().shape, T * board, T * baffle().shape, T * diffuser().shape]
    parts[1].label, parts[2].label, parts[3].label = "board", "baffle", "diffuser"
    clock = bd.Compound(children=parts, label="orbit")
    # The explode: the diffuser off the face, the baffle after it, the board up out of the stand
    face = (T * bd.Pos(0, 0, 1)).position - (T * bd.Pos(0, 0, 0)).position
    up = (T * bd.Pos(0, 1, 0)).position - (T * bd.Pos(0, 0, 0)).position
    face, up = (face.X, face.Y, face.Z), (up.X, up.Y, up.Z)
    show = animation(clock, "explode", duration=6.0)
    show.translation("diffuser", by=tuple(60 * c for c in face), start=0.5, end=2.0)
    show.translation("baffle", by=tuple(32 * c for c in face), start=1.2, end=2.6)
    for name in ("board", "baffle", "diffuser"):
        show.translation(name, by=tuple(45 * c for c in up), start=2.8, end=4.2)
    return clock


if __name__ == "__main__":
    pcb()
    baffle()
    diffuser()
    stand()
    orbit()
    diffuser_print()
    front_print()
