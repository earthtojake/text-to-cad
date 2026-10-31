"""Engineering drawing of the stepped shaft with its keyway.

It calls the model in `stepped_shaft_keyway.py`, which the engine builds (a replay
when it is current). The diameters are dimensioned on the profile, where a turner
reads them, the end view is a section through the keyway, which shows its depth, and
a detail draws the end chamfer large enough to dimension. The keyway is centred on
the shaft, and the top view says so.
"""

from cadgen.eng_drawing import Sheet, eng_drawing
from stepped_shaft_keyway import (
    END_CHAMFER,
    KEYWAY_DEPTH,
    KEYWAY_WIDTH,
    KEYWAY_X_END,
    KEYWAY_X_START,
    LEFT_LENGTH,
    MIDDLE_DIAMETER,
    MIDDLE_LENGTH,
    SMALL_DIAMETER,
    TOTAL_LENGTH,
    stepped_shaft_keyway,
)


@eng_drawing(out="../PDF/stepped_shaft_keyway_drawing.pdf")
def stepped_shaft_keyway_drawing():
    part = stepped_shaft_keyway().shape
    sheet = Sheet(
        "A3", title="STEPPED SHAFT WITH KEYWAY", part_number="SH-120", revision="A", author="text-to-cad",
        general_tolerance="ISO 2768-m",
        notes=["BREAK SHARP EDGES.", f"CHAMFER BOTH ENDS {END_CHAMFER:g} × 45°, SEE DETAIL B."],
    )
    top, front, right, iso = sheet.three_views(part, iso=True)
    middle = (KEYWAY_X_START + KEYWAY_X_END) / 2
    # The end view, cut through the keyway.
    right.section("A", through=(middle, 0, 0))

    r, rs = MIDDLE_DIAMETER / 2, SMALL_DIAMETER / 2
    front.overall(height=False)  # the height is the ⌀30
    front.dim((LEFT_LENGTH / 2, 0, -rs), (LEFT_LENGTH / 2, 0, rs), text="%%c<>")
    front.dim((LEFT_LENGTH + MIDDLE_LENGTH / 2, 0, -r), (LEFT_LENGTH + MIDDLE_LENGTH / 2, 0, r), text="%%c<>")
    front.dim((TOTAL_LENGTH - LEFT_LENGTH / 2, 0, -rs), (TOTAL_LENGTH - LEFT_LENGTH / 2, 0, rs), text="%%c<>")
    front.dim((0, 0, -rs), (LEFT_LENGTH, 0, -rs))
    front.dim((LEFT_LENGTH, 0, -r), (LEFT_LENGTH + MIDDLE_LENGTH, 0, -r))

    top.symmetric("h")                                                       # the keyway is centred
    top.dim((LEFT_LENGTH, KEYWAY_WIDTH / 2, r), (KEYWAY_X_START, KEYWAY_WIDTH / 2, r))
    top.dim((KEYWAY_X_START, KEYWAY_WIDTH / 2, r), (KEYWAY_X_END, KEYWAY_WIDTH / 2, r))
    top.dim((KEYWAY_X_END, -KEYWAY_WIDTH / 2, r), (KEYWAY_X_END, KEYWAY_WIDTH / 2, r))
    right.dim((middle, 0, -r), (middle, 0, r - KEYWAY_DEPTH))  # what is left under the keyway
    # The 1 mm chamfer is too small to dimension at 1:1: a detail draws it larger.
    chamfer = sheet.detail(front, (TOTAL_LENGTH, 0, rs), 4)
    chamfer.dim((TOTAL_LENGTH - END_CHAMFER, 0, rs), (TOTAL_LENGTH, 0, rs))
    chamfer.dim((TOTAL_LENGTH, 0, rs - END_CHAMFER), (TOTAL_LENGTH, 0, rs))
    return sheet


if __name__ == "__main__":
    stepped_shaft_keyway_drawing()
