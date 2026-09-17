"""Engineering drawing of the examples project's electronics enclosure base.

Documents the STEP that models/examples/src/electronics_enclosure_base.py writes:
run that model first (python ../../examples/src/electronics_enclosure_base.py),
then this script. Every view and measured value follows that artifact.
"""

from cadgen.drawing import drawing, Sheet, source_step

# Model facts the dimensions reference (model coordinates, mm); see the model.
L, W, H = 100.0, 70.0, 30.0
WALL, FLOOR = 3.0, 3.0
STANDOFFS = [(-35.0, -25.0), (-35.0, 25.0), (35.0, -25.0), (35.0, 25.0)]
STANDOFF_D, HOLE_D, HOLE_DEPTH = 10.0, 3.0, 8.0


@drawing(out="../DXF/enclosure_drawing.dxf")
def enclosure_drawing():
    part = source_step("../../examples/STEP/electronics_enclosure_base.step")
    sheet = Sheet(
        "A3", title="ELECTRONICS ENCLOSURE BASE", part_number="ENC-001", material="ABS",
        revision="A", author="text-to-cad",
        notes=["BREAK SHARP EDGES.", "NO TOLERANCES SPECIFIED ON THIS SHEET."],
    )
    top, front, right = sheet.three_views(part)
    top.overall()
    top.dim((STANDOFFS[0][0], W / 2, 0), (STANDOFFS[2][0], W / 2, 0), offset=24)
    top.dim((L / 2, STANDOFFS[2][1], 0), (L / 2, STANDOFFS[3][1], 0), offset=12)
    top.diameter((STANDOFFS[3][0], STANDOFFS[3][1], H / 2), HOLE_D / 2, angle=45, text=f"%%c{HOLE_D:g} x {HOLE_DEPTH:g} DEEP, 4 PLACES")
    top.diameter((STANDOFFS[1][0], STANDOFFS[1][1], H / 2), STANDOFF_D / 2, angle=135, text=f"%%c{STANDOFF_D:g} BOSS")
    front.dim((L / 2, -W / 2, 0), (L / 2, -W / 2, H), offset=12)
    right.dim((L / 2, -W / 2, 0), (L / 2, -W / 2 + WALL, 0), offset=-12, text=f"{WALL:g} WALL")
    front.dim((-L / 2, -W / 2, 0), (-L / 2, -W / 2, FLOOR), offset=-12, text=f"{FLOOR:g} FLOOR")
    return sheet


if __name__ == "__main__":
    enclosure_drawing()
