"""Engineering drawing of the electronics enclosure base.

Documents the STEP that `electronics_enclosure_base.py` writes, beside it in this
project: run that model first (`python electronics_enclosure_base.py`), then this
script. Every view and measured value follows that artifact, and every constant a
dimension references is imported from the model, so moving a standoff in the model
moves the dimension here.
"""

from pathlib import Path

import cadgen
from cadgen.eng_drawing import Sheet, eng_drawing
from electronics_enclosure_base import (
    FLOOR_THICKNESS,
    OUTER_HEIGHT,
    OUTER_LENGTH,
    OUTER_WIDTH,
    STANDOFF_DIAMETER,
    STANDOFF_HOLE_DEPTH,
    STANDOFF_HOLE_DIAMETER,
    STANDOFF_LOCATIONS,
    WALL_THICKNESS,
)

STEP = Path(__file__).parent / "../STEP/electronics_enclosure_base.step"


@eng_drawing(out="../PDF/electronics_enclosure_base_drawing.pdf")
def electronics_enclosure_base_drawing():
    part = cadgen.read_step(STEP)
    sheet = Sheet(
        "A3", title="ELECTRONICS ENCLOSURE BASE", part_number="ENC-001", material="ABS",
        revision="A", author="text-to-cad", general_tolerance="ISO 2768-m",
        notes=["BREAK SHARP EDGES."],
    )
    top, front, right = sheet.three_views(part)
    top.overall()
    # Standoff pitch, X then Y, from the model's own locations.
    xs = sorted({x for x, _ in STANDOFF_LOCATIONS})
    ys = sorted({y for _, y in STANDOFF_LOCATIONS})
    top.dim((xs[0], OUTER_WIDTH / 2, 0), (xs[-1], OUTER_WIDTH / 2, 0))
    top.dim((OUTER_LENGTH / 2, ys[0], 0), (OUTER_LENGTH / 2, ys[-1], 0))
    top.hole((xs[-1], ys[-1], OUTER_HEIGHT / 2), STANDOFF_HOLE_DIAMETER,
             depth=STANDOFF_HOLE_DEPTH, count=len(STANDOFF_LOCATIONS))
    # Both callouts leave on the right: a leader that crosses the view is a
    # last resort, and the left-hand standoff has no room for its text.
    top.hole((xs[-1], ys[0], OUTER_HEIGHT / 2), STANDOFF_DIAMETER, thru=True,
             count=len(STANDOFF_LOCATIONS), angle=-45, label="BOSS O.D.")
    front.dim((OUTER_LENGTH / 2, -OUTER_WIDTH / 2, 0), (OUTER_LENGTH / 2, -OUTER_WIDTH / 2, OUTER_HEIGHT))
    front.dim((-OUTER_LENGTH / 2, -OUTER_WIDTH / 2, 0), (-OUTER_LENGTH / 2, -OUTER_WIDTH / 2, FLOOR_THICKNESS),
              offset=-12, text=f"{FLOOR_THICKNESS:g} FLOOR")
    right.dim((OUTER_LENGTH / 2, -OUTER_WIDTH / 2, 0), (OUTER_LENGTH / 2, -OUTER_WIDTH / 2 + WALL_THICKNESS, 0),
              offset=-12, text=f"{WALL_THICKNESS:g} WALL")
    return sheet


if __name__ == "__main__":
    electronics_enclosure_base_drawing()
