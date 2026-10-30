"""Engineering drawing of the circular flange: a plate with a bolt circle.

It calls the model in `circular_flange.py`, which the engine builds (a replay when
it is current). The bolt holes, their pitch circle and the bore are called out from
the part itself; the constants the script references come from the model module.
"""

import math

from cadgen.eng_drawing import Sheet, eng_drawing
from circular_flange import BOLT_CIRCLE_DIAMETER, OUTER_DIAMETER, OUTER_FILLET, THICKNESS, circular_flange


@eng_drawing(out="../PDF/circular_flange_drawing.pdf")
def circular_flange_drawing():
    part = circular_flange().shape
    sheet = Sheet(
        "A4", title="CIRCULAR FLANGE", part_number="FLG-080", revision="A", author="text-to-cad",
        general_tolerance="ISO 2768-m",
    )
    top, front, _right = sheet.three_views(part)
    # Through the middle: the bore and two of the bolt holes, cut.
    front.section("A")

    # A bolt hole off the section line, so its callout and the cutting plane's
    # letter do not share a corner.
    bolt = (BOLT_CIRCLE_DIAMETER / 2 * math.cos(math.radians(60)), BOLT_CIRCLE_DIAMETER / 2 * math.sin(math.radians(60)))
    top.hole((*bolt, THICKNESS))   # 6× ⌀6 THRU EQ SP ON ⌀60: count and pitch circle read off the part
    top.hole((0, 0, THICKNESS), angle=135)                                          # the bore
    top.diameter((0, 0, THICKNESS), size=OUTER_DIAMETER, angle=-45)
    front.overall(width=False)  # the width is the ⌀80
    # The rounded outer edges, seen as arcs at the corners of the section.
    front.radius((OUTER_DIAMETER / 2 - OUTER_FILLET, 0, THICKNESS - OUTER_FILLET), size=OUTER_FILLET, angle=30)
    return sheet


if __name__ == "__main__":
    circular_flange_drawing()
