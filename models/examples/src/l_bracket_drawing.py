"""Engineering drawing of the L-bracket.

It calls the model in `l_bracket.py`, which the engine builds (a replay when it is
current). Both hole patterns are called out from the part, in the views that look
down them; every constant a dimension references comes from the model module. The
bracket is symmetric about its middle across X, and the views that measure X say so:
the spacings across that line place the holes and the gussets either side.
"""

from cadgen.eng_drawing import Sheet, eng_drawing
from l_bracket import (
    BACK_CENTER_Y,
    BACK_HOLE_LOCATIONS,
    BACK_THICKNESS,
    BASE_HOLE_LOCATIONS,
    BASE_LENGTH,
    BASE_THICKNESS,
    BASE_WIDTH,
    GUSSET_DEPTH,
    GUSSET_HEIGHT,
    GUSSET_X_LOCATIONS,
    GUSSET_X_THICKNESS,
    TRANSITION_FILLET,
    l_bracket,
)


@eng_drawing(out="../PDF/l_bracket_drawing.pdf")
def l_bracket_drawing():
    part = l_bracket().shape
    sheet = Sheet(
        "A3", title="L BRACKET", part_number="LB-001", revision="A", author="text-to-cad",
        general_tolerance="ISO 2768-m",
    )
    top, front, right, iso = sheet.three_views(part, iso=True)
    back_face = BACK_CENTER_Y - BACK_THICKNESS / 2  # the back plate's front face

    # Top: the base, its holes and where the gussets stand.
    (x0, y0), (x1, _) = BASE_HOLE_LOCATIONS
    top.overall()
    top.symmetric("v")
    top.holes()
    top.dim((x0, y0, BASE_THICKNESS), (x1, y0, BASE_THICKNESS))
    top.dim((x1, -BASE_WIDTH / 2, BASE_THICKNESS), (x1, y0, BASE_THICKNESS))
    g0, g1 = GUSSET_X_LOCATIONS
    top.dim((g0 - GUSSET_X_THICKNESS / 2, back_face, BASE_THICKNESS),
            (g1 + GUSSET_X_THICKNESS / 2, back_face, BASE_THICKNESS))
    top.dim((g1 - GUSSET_X_THICKNESS / 2, back_face, BASE_THICKNESS),
            (g1 + GUSSET_X_THICKNESS / 2, back_face, BASE_THICKNESS))
    top.dim((g1 + GUSSET_X_THICKNESS / 2, back_face - GUSSET_DEPTH, BASE_THICKNESS),
            (g1 + GUSSET_X_THICKNESS / 2, back_face, BASE_THICKNESS))                 # the gusset's depth

    # Front: the back plate's holes, seen down their axes.
    (bx0, bz0), (bx1, _) = BACK_HOLE_LOCATIONS
    front.overall(width=False)
    front.symmetric("v")
    front.holes()
    front.dim((bx0, back_face, bz0), (bx1, back_face, bz0))
    front.dim((bx0, back_face, 0), (bx0, back_face, bz0))

    # Right: the plate thicknesses and the gusset's height.
    edge = BASE_LENGTH / 2
    top_z = BASE_THICKNESS + GUSSET_HEIGHT
    right.dim((edge, BASE_WIDTH / 2, 0), (edge, BASE_WIDTH / 2, BASE_THICKNESS))
    right.dim((edge, back_face, top_z), (edge, BASE_WIDTH / 2, top_z))
    right.dim((edge, back_face, BASE_THICKNESS), (edge, back_face, top_z))
    # The fillet where the base meets the back plate, seen end-on as an arc.
    right.radius((0, back_face - TRANSITION_FILLET, BASE_THICKNESS + TRANSITION_FILLET), size=TRANSITION_FILLET)
    return sheet


if __name__ == "__main__":
    l_bracket_drawing()
