"""Engineering drawing of the angle bracket: an auxiliary view of its inclined tab.

It calls the model in `angle_bracket.py`, which the engine builds (a replay when it
is current). No principal view shows the tab's face or its hole true, so VIEW C
looks square onto it, and the hole in it is called out there, read off the part. The
front view sees the tab edge-on: its lean off vertical, its thickness and its
lengths up the tab (aligned dimensions, the true lengths) are stated there. Every
position below is the model's constants.
"""

from math import cos, radians, sin

from angle_bracket import (
    BASE_HOLE_X, BASE_LENGTH, TAB_FACE_POINT, TAB_HEIGHT, TAB_HOLE_HEIGHT, TAB_LEAN, THICKNESS, angle_bracket,
)
from cadgen.eng_drawing import Sheet, eng_drawing

LEFT = -BASE_LENGTH / 2
FOOT = (BASE_LENGTH / 2, 0.0, 0.0)  # the tab's outer face meets the bottom here


def along_tab(distance: float, depth: float = 0.0) -> tuple[float, float, float]:
    """The point ``distance`` up the tab from its foot, ``depth`` in from its
    outer face."""
    lean = radians(TAB_LEAN)
    return (FOOT[0] + distance * sin(lean) - depth * cos(lean), 0.0, distance * cos(lean) + depth * sin(lean))


@eng_drawing(out="../PDF/angle_bracket_drawing.pdf")
def angle_bracket_drawing():
    part = angle_bracket().shape
    sheet = Sheet(size=None, scale=None, title="ANGLE BRACKET", part_number="AB-030", revision="A",
                  author="text-to-cad", general_tolerance="ISO 2768-m")
    top, front, right, iso = sheet.three_views(part, iso=True)
    top.overall(width=False)
    top.symmetric("h")                                       # symmetric about its length
    top.holes()
    top.dim((LEFT, 0, THICKNESS), (BASE_HOLE_X, 0, THICKNESS))   # the base hole from the left end
    front.overall(reference=True)                            # the base and the tab fix both
    front.dim((LEFT, 0, 0), FOOT)                            # the base's length, to the tab's foot
    front.dim((LEFT, 0, 0), (LEFT, 0, THICKNESS))            # the base's thickness
    end = along_tab(TAB_HEIGHT)
    front.angle(end, (end[0], 0, end[2] - TAB_HOLE_HEIGHT), FOOT)   # the lean, off vertical
    front.dim(FOOT, along_tab(TAB_HOLE_HEIGHT), orientation="aligned", offset=-10)   # the tab hole, up the tab
    front.dim(FOOT, end, orientation="aligned", offset=-20)  # and the tab's length
    front.dim(end, along_tab(TAB_HEIGHT, THICKNESS), orientation="aligned")   # its thickness
    tab = sheet.auxiliary(front, TAB_FACE_POINT)   # VIEW C, square onto the tab
    tab.holes()
    return sheet


if __name__ == "__main__":
    angle_bracket_drawing()
