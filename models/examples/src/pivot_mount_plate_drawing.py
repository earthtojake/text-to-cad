"""Engineering drawing of the pivot mounting plate: GD&T on an aerospace sheet.

It calls the model in `pivot_mount_plate.py`, which the engine builds (a replay when
it is current), reads the parts list off the assembly it hands back, and draws two
sheets: the plate with its lined bushing installed, cut through the bushing and
hatched by material, and the machined plate itself, toleranced to datums A, B and C.
Every position below is a constant of the model module; every hole size is read off
the part.

The requirements -- the datums and frames, the bore's fit and the installed bore's
limits, the key characteristics, materials, specs, finish and how the bushing is
held -- are EXAMPLE values, written the way a design-intent interview records what
the person confirmed. They are not a released design, and every sheet says so. The
company's profile is its own: ASME Y14.5-2018, CAGE CODE and DISTRIBUTION cells, and
its two release categories.
"""

from cadgen.eng_drawing import Frame, Profile, Sheet, eng_drawing, parts_list
from pivot_mount_plate import (
    BOLT_HOLES, BORE_DIAMETER, BORE_X, BORE_Y, BUSHING_BORE, CORNER_RADIUS, LINER_THICKNESS, PIN_DIAMETER,
    PLATE_LENGTH, PLATE_THICKNESS, PLATE_WIDTH, pivot_mount_plate,
)

EXAMPLE = "EXAMPLE REQUIREMENTS FOR DEMONSTRATION; NOT A RELEASED DESIGN."
DISTRIBUTION = "DISTRIBUTION STATEMENT A. APPROVED FOR PUBLIC RELEASE; DISTRIBUTION IS UNLIMITED."
TITLE, NUMBER = "PIVOT MOUNT PLATE ASSY", "PMP-100"
#: The design activity's profile: the standard it tolerances by, the cells an
#: aerospace drawing carries, and its own names for the stages it releases at.
EXAMPLE_AERO = Profile("EXAMPLE AERO", "ASME Y14.5-2018", {"PRELIMINARY": "prototype", "RELEASED": "production"},
                       fields=("CAGE CODE", "DISTRIBUTION"))
RELEASE = dict(revision="A", author="text-to-cad", profile=EXAMPLE_AERO, category="RELEASED",
               company="EXAMPLE AERO CO.", fields={"CAGE CODE": "0ABC1", "DISTRIBUTION": "A"})


@eng_drawing(out="../PDF/pivot_mount_plate_drawing.pdf")
def pivot_mount_plate_drawing():
    parts = parts_list(pivot_mount_plate().shape)
    parts.set("mount_plate", part_number="PMP-101", material="AL 7075-T651", spec="AMS 4045",
              family="aluminium")
    parts.set("bushing", description="BUSHING, LINED", material="CRES 303", spec="AMS 5640", family="steel")
    parts.set("liner", description="LINER, BUSHING", material="PTFE FABRIC", spec="AS81934", family="fabric")
    return [_assembly_sheet(parts), _plate_sheet(parts)]


def _assembly_sheet(parts) -> Sheet:
    """The bushing installed: a section through it, each part hatched as its
    material, the layers of the lined bushing in a note, the installed bore's limits."""
    layers = (f"ITEM 2 WALL {(BORE_DIAMETER - BUSHING_BORE) / 2:g} THK, SLEEVE, FULL LENGTH; "
              f"ITEM 3 {LINER_THICKNESS:g} THK, BORE, FULL LENGTH.")
    sheet = Sheet("A3", 2.0, title=TITLE, part_number=NUMBER, notes=[EXAMPLE, DISTRIBUTION, layers], **RELEASE)
    front, right = sheet.three_views(parts.assembly, views=("front", "right"))
    front.section("A", through=(BORE_X, BORE_Y, 0), parts=parts, materials=True)
    front.overall(reference=True)
    right.overall(height=False, reference=True)
    front.balloons(parts)
    y = BORE_Y   # the section plane: points on it lie on the cut faces
    # The bore the pivot pin runs in, inspected once the bushing is in.
    front.dim((BORE_X - PIN_DIAMETER / 2, y, PLATE_THICKNESS), (BORE_X + PIN_DIAMETER / 2, y, PLATE_THICKNESS),
              text="%%c<>", limits=(12.000, 12.025), key=True)
    # The bushing's wall, larger: the liner hatched as fabric, and how each layer is held.
    liner, sleeve = BORE_X + BUSHING_BORE / 2, BORE_X + BORE_DIAMETER / 2
    wall = sheet.detail(front, ((liner + sleeve) / 2, y, PLATE_THICKNESS / 2), 4)
    wall.flag("ITEM 2 INTO ITEM 1, FLUSH WITHIN 0.1 BOTH FACES", at=(sleeve, y, PLATE_THICKNESS / 2),
              joint="press_fit")
    wall.flag("ITEM 3 TO ITEM 2 PER AS81934", at=(liner, y, PLATE_THICKNESS / 2), joint="bond")
    sheet.parts_list(parts)
    return sheet


def _plate_sheet(parts) -> Sheet:
    """The machined plate: datums A, B and C on the faces it mounts on and is pushed
    against, the hole pattern and the bore positioned to them by basic dimensions."""
    plate = parts["mount_plate"]
    sheet = Sheet(size=None, scale=None, title="MOUNT PLATE", subtitle=f"ITEM 1 (QTY 1) OF {TITLE}", part_number=NUMBER,
                  material="AL 7075-T651", spec="AMS 4045", finish="CHEM FILM PER MIL-DTL-5541 TY II CL 3",
                  general_tolerance="±0.1", notes=[EXAMPLE, DISTRIBUTION, "BREAK SHARP EDGES 0.1-0.4."], **RELEASE)
    top, front, right, _iso = sheet.three_views(plate.shape, iso=True)
    t = PLATE_THICKNESS
    # The datum reference frame: the mounting face flat, the side face square to it,
    # the end face square to both.
    front.datum("A", (PLATE_LENGTH / 4, BORE_Y, 0))
    front.frame((3 * PLATE_LENGTH / 4, BORE_Y, 0), Frame("flatness", 0.05), offset=(12, -12))
    right.datum("B", (BORE_X, 0, t / 2))
    right.frame((BORE_X, 0, t), Frame("perpendicularity", 0.05, ("A",)), offset=(-10, 12))
    front.datum("C", (0, BORE_Y, t / 2))
    front.frame((0, BORE_Y, 3 * t / 4), Frame("perpendicularity", 0.05, ("A", "B")))

    top.overall()
    front.overall(width=False)
    # The bolt pattern and the bore, each at its true position from B and C.
    (x0, y0), (x1, _), (_, y1) = BOLT_HOLES[0], BOLT_HOLES[1], BOLT_HOLES[2]
    top.dim((0, PLATE_WIDTH - CORNER_RADIUS, t), (x0, y1, t), orientation="h", basic=True)
    top.dim((x0, y1, t), (x1, y1, t), basic=True)
    top.dim((0, CORNER_RADIUS, t), (BORE_X, BORE_Y, t), orientation="h", basic=True)
    top.dim((PLATE_LENGTH - CORNER_RADIUS, 0, t), (x1, y0, t), orientation="v", basic=True)
    top.dim((x1, y0, t), (x1, y1, t), basic=True)
    top.dim((CORNER_RADIUS, 0, t), (BORE_X, BORE_Y, t), orientation="v", basic=True)
    top.hole((x1, y1, t), frame=Frame("position", 0.25, ("A", "B", "C"), diameter=True, modifier="M"))
    top.hole((BORE_X, BORE_Y, t), fit="H7", frame=Frame("position", 0.05, ("A", "B", "C"), diameter=True),
             key=True)
    top.radius((PLATE_LENGTH - CORNER_RADIUS, PLATE_WIDTH - CORNER_RADIUS, t), size=CORNER_RADIUS)
    return sheet


if __name__ == "__main__":
    pivot_mount_plate_drawing()
