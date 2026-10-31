"""Engineering drawing of the guide bar: a broken view of a long part.

It calls the model in `guide_bar.py`, which the engine builds (a replay when it is
current). The bar's middle is the same section all along, so the front and top views
leave it out between two break lines, and the sheet chooses its own size and scale
for what is left. The overall length is still stated true.
"""

from cadgen.eng_drawing import Sheet, eng_drawing
from guide_bar import (
    CROSS_HOLE_INSET, DIAMETER, END_CHAMFER, LENGTH, SPIGOT_DIAMETER, SPIGOT_LENGTH, guide_bar,
)


@eng_drawing(out="../PDF/guide_bar_drawing.pdf")
def guide_bar_drawing():
    part = guide_bar().shape
    sheet = Sheet(size=None, scale=None, title="GUIDE BAR", part_number="GB-600", revision="A",
                  author="text-to-cad", general_tolerance="ISO 2768-m")
    top, front, right, iso = sheet.three_views(part, iso=True)
    front.broken((LENGTH / 6, 0, 0), (LENGTH * 5 / 6, 0, 0))   # the top view breaks with it
    front.overall(height=False)                                # the height is the diameter
    r, s = DIAMETER / 2, SPIGOT_DIAMETER / 2
    front.dim((LENGTH / 12, 0, -r), (LENGTH / 12, 0, r), text="%%c<>")    # left of the break
    front.dim((LENGTH + SPIGOT_LENGTH / 2, 0, -s), (LENGTH + SPIGOT_LENGTH / 2, 0, s), text="%%c<>")
    front.dim((LENGTH, 0, -r), (LENGTH + SPIGOT_LENGTH, 0, -r))
    front.dim((0, 0, r), (CROSS_HOLE_INSET, 0, r))                         # the left cross hole from the end
    front.dim((LENGTH - CROSS_HOLE_INSET, 0, r), (LENGTH, 0, r))           # the right one from the shoulder
    front.note(f"{END_CHAMFER:g} × 45°", (END_CHAMFER / 2, 0, -r + END_CHAMFER / 2), offset=(-10, -10))
    top.holes()
    return sheet


if __name__ == "__main__":
    guide_bar_drawing()
