"""Engineering drawing of the mounting plate: holes, a slot, a corner radius.

It calls the model in `mounting_plate.py`, which the engine builds (a replay when it
is current; the run writes that model's declared STL, 3MF and GLB too). The holes
and the slot are called out from the part itself. The model keeps its sizes inside
`lib.simple_model_library.make_mounting_plate`, so the positions below are that
function's numbers, read from its source. The plate is symmetric about its
horizontal centre line, and the drawing says so: the bore and the slot are on it,
and the holes' spacing across it puts them half of it either side. The slot is on
one side only, so along X the holes and the bore are placed from the left edge.
"""

from cadgen.eng_drawing import Sheet, eng_drawing
from mounting_plate import mounting_plate


# From make_mounting_plate(): a 100 x 70 x 8 plate, ⌀5.5 holes at (±38, ±24), the
# slot centred at x = 32 running along Y, R5 corners.
THICKNESS = 8.0
HOLE_X, HOLE_Y = 38.0, 24.0
SLOT_X = 32.0
CORNER = (50.0 - 5.0, 35.0 - 5.0)
LEFT = -50.0


@eng_drawing(out="../PDF/mounting_plate_drawing.pdf")
def mounting_plate_drawing():
    part = mounting_plate().shape
    sheet = Sheet("A3", title="MOUNTING PLATE", part_number="MP-100", revision="A", author="text-to-cad",
                  general_tolerance="ISO 2768-m", notes=["OUTSIDE EDGES ROUNDED R0.8.", "BREAK SHARP EDGES."])
    top, front, right, iso = sheet.three_views(part, iso=True)
    top.overall()
    top.symmetric("h")                                                   # symmetric about its length
    top.holes()                                                          # holes and the slot, from the part
    top.dim((LEFT, HOLE_Y, THICKNESS), (-HOLE_X, HOLE_Y, THICKNESS))     # the pattern from the left edge
    top.dim((LEFT, 0, THICKNESS), (0, 0, THICKNESS))                     # and the bore
    top.dim((-HOLE_X, HOLE_Y, THICKNESS), (HOLE_X, HOLE_Y, THICKNESS))   # hole pitch in X
    top.dim((HOLE_X, -HOLE_Y, THICKNESS), (HOLE_X, HOLE_Y, THICKNESS))   # and in Y
    top.dim((0, -HOLE_Y, THICKNESS), (SLOT_X, -HOLE_Y, THICKNESS))       # the slot's centre from the bore's
    top.radius(CORNER + (THICKNESS,), size=5, angle=60)
    front.overall(width=False)
    return sheet


if __name__ == "__main__":
    mounting_plate_drawing()
