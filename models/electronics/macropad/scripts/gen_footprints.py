"""This project's footprint library, macropad.pretty:

- SW_Kailh_HotSwap_MX_1.00u: KiCad's library (10.99, Button_Switch_Keyboard) has MX footprints for
  soldered switches only, no hot-swap socket. Drawn here from the Kailh CPG151101S11 socket's land
  pattern and the Cherry MX hole pattern (KiCad's SW_Cherry_MX_1.00u_PCB, its centre hole moved to the
  origin): centre post 4.0 mm, PCB-mount pegs 1.75 mm at +-5.08, switch pins in 3.0 mm holes (the
  socket's cups), the socket's two SMD terminals 2.55 x 2.5 mm. The socket sits under the board, so the
  footprint is drawn as a top-side part mirrored in x and the board flips it: after the flip, pin 1's
  hole is at (2.54, -5.08) and its pad at (5.842, -5.08); pin 2's at (-3.81, -2.54) and (-7.085, -2.54),
  as the board is seen from above. Its B.* graphics land on the top: the 14 mm switch cut-out (F.Fab)
  and the switch's courtyard (F.CrtYd), so DRC keeps the encoder clear of the switches.
- RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm: KiCad's own, with a 3D model (KiCad ships none
  for it) from src/vendor_parts.py.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
LIB = os.path.join(PROJ, "macropad.pretty")
STOCK = os.environ.get("KICAD10_FOOTPRINT_DIR", "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
sys.path.insert(0, HERE)
from schlib import uid  # noqa: E402


def U(*k):
    return f'(uuid "{uid("fp", *k)}")'


def line(x0, y0, x1, y1, layer, w=0.12, key=""):
    return (f'\t(fp_line (start {x0:g} {y0:g}) (end {x1:g} {y1:g}) (stroke (width {w}) (type solid)) '
            f'(layer "{layer}") {U("line", layer, x0, y0, x1, y1, key)})')


def poly(pts, layer, w=0.05):
    xy = " ".join(f"(xy {x:g} {y:g})" for x, y in pts)
    return f'\t(fp_poly (pts {xy}) (stroke (width {w}) (type solid)) (fill no) (layer "{layer}") {U("poly", layer, pts[0])})'


def hotswap():
    m = lambda x: -x  # drawn mirrored: the board flips it to the bottom
    socket_top = [(-6.1, -0.25), (-2.0, -0.25), (-2.0, -2.78), (4.84, -2.78), (4.84, -7.38), (0.24, -7.38),
                  (0.24, -4.85), (-6.1, -4.85)]
    court_top = [(-8.61, -0.0), (-2.15, -0.0), (-2.15, -2.53), (7.37, -2.53), (7.37, -7.63), (-0.01, -7.63),
                 (-0.01, -5.1), (-8.61, -5.1)]
    out = ['(footprint "SW_Kailh_HotSwap_MX_1.00u"', '\t(version 20241229)', '\t(generator "pcbnew")',
           '\t(generator_version "9.0")', '\t(layer "F.Cu")',
           '\t(descr "Cherry MX-style switch in a Kailh CPG151101S11 hot-swap socket, 1.00u (19.05 mm). '
           'Place on the bottom (flip): the socket solders to the bottom copper. https://www.kailhswitch.com/")',
           '\t(tags "Cherry MX keyboard keyswitch hotswap Kailh socket")',
           f'\t(property "Reference" "REF**" (at {m(-3.0):g} -8.6 0) (layer "F.SilkS") {U("ref")} '
           '(effects (font (size 1 1) (thickness 0.15))))',
           f'\t(property "Value" "SW_Kailh_HotSwap_MX_1.00u" (at 0 8.5 0) (layer "F.Fab") {U("val")} '
           '(effects (font (size 1 1) (thickness 0.15))))',
           f'\t(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) {U("ds")} (effects (font (size 1.27 1.27))))',
           f'\t(property "Description" "" (at 0 0 0) (layer "F.Fab") (hide yes) {U("de")} (effects (font (size 1.27 1.27))))',
           '\t(attr smd)']
    # socket body on the fab layer (the bottom after the flip); on the silkscreen only its two outer
    # edges, clear of the pads and holes, so the socket's place reads on the bare board
    for a_, b_ in (((-6.1, -0.25), (-6.1, -1.0)), ((4.84, -7.38), (0.6, -7.38))):
        out.append(line(m(a_[0]), a_[1], m(b_[0]), b_[1], "F.SilkS", 0.12, "silk"))
    for layer, pts in (("F.Fab", socket_top),):
        pts = [(m(x), y) for x, y in pts]
        for a, b in zip(pts, pts[1:] + pts[:1]):
            out.append(line(a[0], a[1], b[0], b[1], layer, 0.12 if layer == "F.SilkS" else 0.1, "s"))
    out.append(poly([(m(x), y) for x, y in court_top], "F.CrtYd"))
    # the switch on the other side: its 14 mm plate cut-out and 15.6 mm top housing
    for layer, h, w in (("B.Fab", 7.0, 0.1), ("B.CrtYd", 7.8, 0.05)):
        c = [(-h, -h), (h, -h), (h, h), (-h, h)]
        for a, b in zip(c, c[1:] + c[:1]):
            out.append(line(a[0], a[1], b[0], b[1], layer, w, "sw"))
    out.append(f'\t(fp_text user "${{REFERENCE}}" (at 0 3.2 0) (layer "B.Fab") {U("reftext")} '
               '(effects (font (size 1 1) (thickness 0.15)) (justify mirror)))')
    npth = [(0, 0, 4.0), (5.08, 0, 1.75), (-5.08, 0, 1.75), (m(2.54), -5.08, 3.0), (m(-3.81), -2.54, 3.0)]
    for i, (x, y, d) in enumerate(npth):
        out.append(f'\t(pad "" np_thru_hole circle (at {x:g} {y:g}) (size {d:g} {d:g}) (drill {d:g}) '
                   f'(layers "*.Cu" "*.Mask") {U("npth", i)})')
    for num, (x, y) in (("1", (m(5.842), -5.08)), ("2", (m(-7.085), -2.54))):
        out.append(f'\t(pad "{num}" smd roundrect (at {x:g} {y:g}) (size 2.55 2.5) (layers "F.Cu" "F.Mask" "F.Paste") '
                   f'(roundrect_rratio 0.1) {U("pad", num)})')
    out.append('\t(model "${KIPRJMOD}/macropad.3dshapes/Kailh_CPG151101S11_HotSwap_MX.step" '
               '(offset (xyz 0 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))')
    out.append('\t(embedded_fonts no)')
    out.append(')')
    return "\n".join(out) + "\n"


def encoder():
    name = "RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm"
    text = open(f"{STOCK}/Rotary_Encoder.pretty/{name}.kicad_mod", encoding="utf-8").read()
    text = re.sub(r'\(model "[^"]*"', '(model "${KIPRJMOD}/macropad.3dshapes/Alps_EC11E_Switch_H20mm.step"', text, count=1)
    return text


os.makedirs(LIB, exist_ok=True)
with open(os.path.join(LIB, "SW_Kailh_HotSwap_MX_1.00u.kicad_mod"), "w", encoding="utf-8") as fh:
    fh.write(hotswap())
with open(os.path.join(LIB, "RotaryEncoder_Alps_EC11E-Switch_Vertical_H20mm.kicad_mod"), "w", encoding="utf-8") as fh:
    fh.write(encoder())
print("wrote", LIB)
