"""Engineering drawing of the electronics enclosure base.

Documents the model `electronics_enclosure_base.py` defines, beside it in this
project: the drawing calls it, so the engine builds it (a replay when it is current) and
hands back its shape. Every view and measured value follows that model, every hole
callout is read off it, and every constant a dimension references is imported from it,
so moving a standoff in the model moves the dimension here. The base is symmetric
about both centre lines, and the drawing says so: one wall each way, and the
standoff spacings across the centre lines, place the rest.
"""

from cadgen.eng_drawing import Sheet, eng_drawing

from electronics_enclosure_base import (
    FLOOR_THICKNESS,
    OUTER_CORNER_FILLET_RADIUS,
    OUTER_HEIGHT,
    OUTER_LENGTH,
    OUTER_WIDTH,
    STANDOFF_DIAMETER,
    STANDOFF_HEIGHT,
    STANDOFF_LOCATIONS,
    WALL_THICKNESS,
    electronics_enclosure_base,
)


@eng_drawing(out="../PDF/electronics_enclosure_base_drawing.pdf")
def electronics_enclosure_base_drawing():
    part = electronics_enclosure_base().shape
    sheet = Sheet(
        "A3", title="ELECTRONICS ENCLOSURE BASE", part_number="ENC-001", material="ABS",
        revision="A", author="text-to-cad", general_tolerance="ISO 2768-m",
        notes=["BREAK SHARP EDGES."],
    )
    top, front, right, iso = sheet.three_views(part, iso=True)
    xs = sorted({x for x, _ in STANDOFF_LOCATIONS})
    ys = sorted({y for _, y in STANDOFF_LOCATIONS})
    # The front view cut through the front pair of standoffs: the wall, the floor
    # and a standoff's bore in section, where hidden lines could only hint at them.
    front.section("A", through=(0, ys[0], 0))

    top.overall()
    top.symmetric("h").symmetric("v")                                        # symmetric both ways
    top.dim((xs[0], ys[-1], OUTER_HEIGHT), (xs[-1], ys[-1], OUTER_HEIGHT))   # standoff pitch in X
    top.dim((xs[-1], ys[0], OUTER_HEIGHT), (xs[-1], ys[-1], OUTER_HEIGHT))   # and in Y
    top.holes()                                                              # 4× ⌀3 ↧8, from the part
    top.diameter((xs[-1], ys[-1], 0), size=STANDOFF_DIAMETER)                 # the boss around each hole
    corner = OUTER_CORNER_FILLET_RADIUS
    top.radius((-OUTER_LENGTH / 2 + corner, OUTER_WIDTH / 2 - corner, OUTER_HEIGHT), size=corner, angle=135)

    y = ys[0]  # the section plane: points on it lie on the cut faces
    front.overall(width=False)  # the width is the top view's
    front.dim((OUTER_LENGTH / 2, y, 0), (OUTER_LENGTH / 2, y, FLOOR_THICKNESS))
    front.dim((-OUTER_LENGTH / 2, y, OUTER_HEIGHT), (-OUTER_LENGTH / 2 + WALL_THICKNESS, y, OUTER_HEIGHT))
    front.dim((xs[0], y, FLOOR_THICKNESS), (xs[0], y, FLOOR_THICKNESS + STANDOFF_HEIGHT))
    right.dim((0, OUTER_WIDTH / 2, OUTER_HEIGHT), (0, OUTER_WIDTH / 2 - WALL_THICKNESS, OUTER_HEIGHT))   # a side wall
    return sheet


if __name__ == "__main__":
    electronics_enclosure_base_drawing()
