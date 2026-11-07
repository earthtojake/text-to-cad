"""Bought parts KiCad's library has no 3D model for, modelled from their datasheets' outline drawings
(simplified bodies, for fit checks and pictures, not for tooling):

- kailh_socket: Kailh CPG151101S11 MX hot-swap socket. Modelled in its footprint's own frame
  (macropad.pretty/SW_Kailh_HotSwap_MX_1.00u: a top-side footprint drawn mirrored, which the board
  flips to the bottom), z up from the copper it sits on.
- ec11_encoder: Alps EC11E with push switch, 20 mm shaft (EC11E18244A5): the frame of KiCad's
  footprint RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm (origin at pad A, y up as KiCad's 3D
  models are), z up from the board's top.
- mx_switch: a Cherry MX-style switch, for the assembly: origin at its centre on the PCB's top face,
  z up. The plate's top is 5.0 mm above it, the housing's top 11.6 mm, the stem's 16.6 mm.

The socket and the encoder each declare the STEP the project's footprints name
(`${KIPRJMOD}/macropad.3dshapes/...`), which every run writes: run the script before opening the board in
3D or exporting its STEP or GLB. The folder is gitignored.

    cad run src/vendor_parts.py
"""
import build123d as bd
from cad import model, step

SOCKET_H = 1.85  # body height (Kailh CPG151101S11 drawing: 1.8 mm nominal)


def _box(x0, x1, y0, y1, z0, z1):
    return bd.Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * bd.Box(x1 - x0, y1 - y0, z1 - z0)


@step("../macropad.3dshapes/Kailh_CPG151101S11_HotSwap_MX.step")
def kailh_socket():
    # top view (as the board is looked at from above, KiCad's y down) of the socket under a switch
    # centred at 0,0.
    body = bd.Polyline((-6.1, -0.25), (-2.0, -0.25), (-2.0, -2.78), (4.84, -2.78), (4.84, -7.38),
                       (0.24, -7.38), (0.24, -4.85), (-6.1, -4.85), close=True)
    solid = bd.extrude(bd.make_face(body), SOCKET_H)
    # pin cups: the switch's pins (1.5 mm) drop into them
    for x, y in ((2.54, -5.08), (-3.81, -2.54)):
        solid -= bd.Pos(x, y, 0) * bd.Cylinder(1.1, SOCKET_H * 3)
    # solder terminals out to the two pads
    solid += _box(4.84, 7.0, -5.93, -4.23, 0, 0.3)
    solid += _box(-8.25, -6.1, -3.39, -1.69, 0, 0.3)
    # footprint frame: x mirrored (drawn for a flip); a 3D model's frame: y up. Together, a half turn.
    solid = bd.Rot(0, 0, 180) * solid
    solid.label = "kailh_socket"
    solid.color = "#2b2b2b"
    return solid


@step("../macropad.3dshapes/Alps_EC11E_Switch_H20mm.step")
def ec11_encoder():
    sx, sy = 7.5, -2.5  # shaft centre (footprint (7.5, 2.5), y down -> model y up)
    body = _box(sx - 5.85, sx + 5.85, sy - 6.2, sy + 6.2, 0, 6.5)
    body.color = "#b8b8b8"
    bushing = bd.Pos(sx, sy, 6.5) * bd.Cylinder(3.5, 5.0, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    shaft = bd.Pos(sx, sy, 11.5) * bd.Cylinder(3.0, 8.5, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    flat = _box(sx + 1.5, sx + 3.5, sy - 3.5, sy + 3.5, 13.0, 20.5)  # D-flat: 4.5 mm across, top 7 mm
    shaft = shaft - flat
    pins = [bd.Pos(x, y, -1.75) * bd.Box(0.8, 0.3, 3.5) for x, y in ((0, 0), (0, -2.5), (0, -5), (14.5, 0), (14.5, -5))]
    tabs = [bd.Pos(sx, y, -1.0) * bd.Box(2.0, 0.5, 2.0) for y in (3.1, -8.1)]
    metal = bushing + shaft
    for p in pins + tabs:
        metal += p
    metal.color = "#d4d4d4"
    out = bd.Compound(children=[body, metal], label="ec11_encoder")
    body.label, metal.label = "body", "metal"
    return out


def mx_switch_body():
    bottom = _box(-6.95, 6.95, -6.95, 6.95, 0, 5.0)          # through the 14 mm plate cut-out
    top = bd.loft([bd.Pos(0, 0, 5.0) * bd.Rectangle(15.6, 15.6), bd.Pos(0, 0, 11.6) * bd.Rectangle(11.6, 11.6)])
    housing = bottom + top
    post = bd.Pos(0, 0, -3.3) * bd.Cylinder(1.95, 3.3, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
    housing += post
    housing.color = "#1d1d1f"
    slider = _box(-3.6, 3.6, -2.8, 2.8, 11.6, 12.6)
    cross = _box(-2.0, 2.0, -0.585, 0.585, 12.6, 16.6) + _box(-0.585, 0.585, -2.0, 2.0, 12.6, 16.6)
    stem = slider + cross
    stem.color = "#c8102e"
    return housing, stem


@model
def mx_switch():
    housing, stem = mx_switch_body()
    # pins, in the assembly's frame (y up): KiCad's (2.54, -5.08) and (-3.81, -2.54) are (2.54, 5.08), (-3.81, 2.54)
    pins = None
    for x, y in ((2.54, 5.08), (-3.81, 2.54)):
        p = bd.Pos(x, y, -3.3) * bd.Cylinder(0.6, 3.3, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        pins = p if pins is None else pins + p
    pins.color = "#c9a227"
    housing.label, stem.label, pins.label = "housing", "stem", "pins"
    return bd.Compound(children=[housing, stem, pins], label="mx_switch")


if __name__ == "__main__":
    kailh_socket()
    ec11_encoder()
    mx_switch()
