"""Panel hardware: a Davies 1900H-style knob, the Thonkiconn hex nut, the jacks' spacer washer and the pots'
M7 nut, each modelled at the origin on +Z (its base at z = 0).

Davies 1900H (clone listings: Tayda, Maplin, Grobotronics): 12.7 mm at the base, 11.9 mm at the top,
15.8 mm tall, fluted, white pointer line; here bored 6.0 mm for the Alpha pot's 6 mm knurled shaft.
Thonkiconn nut: M6 x 0.5, 8 mm across flats, 2 mm. Alpha RD901F nut: M7 x 0.75, 10 mm across flats, 2 mm.

Run: cad run src/hardware.py"""

import math

import build123d as bd
from cad import model

from lib.twin_orbit import JACK_SPACER_T

KNOB_BASE_D, KNOB_TOP_D, KNOB_H = 12.7, 11.9, 15.8
KNOB_SKIRT_D, KNOB_SKIRT_H = 14.2, 1.6
KNOB_BORE_D, KNOB_BORE_DEPTH = 6.05, 11.0
FLUTES = 24


def knob_body():
    """Revolved profile (skirt, tapered body, chamfered top, blind bore), then 24 flutes. A union of
    build123d Cones and a Cylinder came out as an inverted solid (negative volume)."""
    mn = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    r_bore = KNOB_BORE_D / 2
    profile = [(r_bore, 0), (KNOB_SKIRT_D / 2, 0), (KNOB_SKIRT_D / 2, KNOB_SKIRT_H), (KNOB_BASE_D / 2, KNOB_SKIRT_H),
               (KNOB_TOP_D / 2, KNOB_H - 0.6), (KNOB_TOP_D / 2 - 0.6, KNOB_H), (0, KNOB_H), (0, KNOB_BORE_DEPTH),
               (r_bore, KNOB_BORE_DEPTH)]
    with bd.BuildPart() as p:
        with bd.BuildSketch(bd.Plane.XZ):
            bd.Polygon(*profile, align=None)
        bd.revolve(axis=bd.Axis.Z)
    flutes = [bd.Pos(0, 0, KNOB_SKIRT_H + 0.6) * bd.Rot(0, 0, 360 * i / FLUTES) * bd.Pos(KNOB_BASE_D / 2 + 0.1, 0, 0)
              * bd.Cylinder(0.5, KNOB_H, align=mn) for i in range(FLUTES)]
    body = p.part - bd.Compound(flutes)
    assert body.volume > 0, body.volume
    body.label, body.color = "cap", "#121214"
    pointer = bd.Pos(0, KNOB_TOP_D / 4 + 0.4, KNOB_H) * bd.Box(0.7, KNOB_TOP_D / 2 - 1.6, 0.04, align=mn)
    pointer.label, pointer.color = "pointer", "#f4f4f0"
    return bd.Compound(children=[body, pointer], label="knob")


def hex_nut(af, thick, hole, label):
    r = af / 2 / math.cos(math.radians(30))
    nut = bd.extrude(bd.RegularPolygon(r, 6), thick) - bd.Cylinder(hole / 2, thick * 3)
    nut = nut & bd.Cone(r + 0.25, r - 0.35, thick, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))  # chamfered corners
    nut.label, nut.color = label, "#c9cbce"
    return nut


def washer(od, id_, thick, label, color):
    w = bd.Cylinder(od / 2, thick, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)) - bd.Cylinder(id_ / 2, thick * 3)
    w.label, w.color = label, color
    return w


@model
def knob():
    return knob_body()


@model
def jack_nut():
    return hex_nut(8.0, 2.0, 6.05, "jack_nut")


@model
def pot_nut():
    return hex_nut(10.0, 2.0, 7.05, "pot_nut")


@model
def jack_spacer():
    return washer(8.6, 6.3, JACK_SPACER_T, "jack_spacer", "#3a3a3a")


if __name__ == "__main__":
    knob()
    jack_nut()
    pot_nut()
    jack_spacer()
