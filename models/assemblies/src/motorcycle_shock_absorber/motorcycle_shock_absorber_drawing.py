"""Assembly drawing of the motorcycle shock absorber: a general arrangement, a
section through it part by part, and a sheet for each part.

It calls the model in `motorcycle_shock_absorber.py`, which the engine builds (a
replay when it is current), and reads the parts list off the assembly it hands back.
The model names its two mounting eyes apart (lower, upper), so they arrive as two
items; they are one part, made twice, and merge() lists them as one after checking
their shapes are the same.

The requirements below -- materials and their specs, the threadlocker and the
grease, how each joint is held, the eye bore's fit, the collar's thread and the
tube's -- are EXAMPLE values, written the way a design-intent interview records what the
person confirmed. They are not a released design, and every sheet says so. The
run prints what each sheet still leaves unstated and the joints still to settle.

The coil spring is the one simplified part: the model draws its coil as straight
segments, so its sheet says so and gives the spring's data, and lists what is not
yet specified.
"""

from cadgen.eng_drawing import GENERIC, Sheet, assembly_sheets, eng_drawing, parts_list
from motorcycle_shock_absorber import (
    BODY_OD, BODY_TOP_Z, PRELOAD_COLLAR_TOP_Z, SPRING_BOTTOM_Z, SPRING_HEIGHT, SPRING_MEAN_D, SPRING_TURNS,
    SPRING_WIRE_D, motorcycle_shock_absorber,
)

#: The tube's thread runs this far down from its top end: the collar's travel.
THREAD_LENGTH = 40.0

EXAMPLE = "EXAMPLE REQUIREMENTS FOR DEMONSTRATION; NOT A RELEASED DESIGN."
TITLE, NUMBER = "MOTORCYCLE SHOCK ABSORBER", "MSA-100"


@eng_drawing(out="../../PDF/motorcycle_shock_absorber/motorcycle_shock_absorber_drawing.pdf")
def motorcycle_shock_absorber_drawing():
    parts = parts_list(motorcycle_shock_absorber().shape)
    parts.merge("mounting_eye:lower", "mounting_eye:upper")
    # What each part is made of: example values, as the interview recorded them.
    for key, material, spec, family in (
            ("mounting_eye", "STEEL 4140 Q&T", "ASTM A29", "steel"),
            ("eye_shank", "STEEL 1020", "ASTM A29", "steel"),
            ("pressure_tube", "1026 DOM TUBE", "ASTM A513", "steel"),
            ("gland_cap", "AL 6061-T6", "ASTM B211", "aluminium"),
            ("preload_adjuster_collar", "AL 7075-T6", "ASTM B211", "aluminium"),
            ("lower_spring_seat", "STEEL 1018", "ASTM A108", "steel"),
            ("rebound_adjuster_knob", "AL 6061-T6", "ASTM B211", "aluminium"),
            ("piston_rod", "STEEL 4140", "ASTM A29", "steel"),
            ("upper_spring_seat", "AL 6061-T6", "ASTM B211", "aluminium"),
            ("coil_spring", "CR-SI WIRE", "ASTM A401", "steel")):
        parts.set(key, material=material, spec=spec, family=family)
    locker = parts.add("THREADLOCKER, GRADE N", spec="MIL-S-46163 TYPE II")
    grease = parts.add("GREASE, NLGI 2")

    sheets = assembly_sheets(parts, title=TITLE, part_number=NUMBER, revision="A", author="text-to-cad",
                             general_tolerance="ISO 2768-m", stage="prototype", profile=GENERIC,
                             notes=[EXAMPLE])
    # How each joint is held, flagged where it is on the general arrangement.
    front = next(view for view in sheets[0].views if view.name == "front")
    front.flag("SET SPRING PRELOAD 6 MM, LOCK WITH SPANNER TO 40 NM", item="preload_adjuster_collar")
    front.flag(f"ITEM {locker.number} ON THREAD, TORQUE TO 25 NM", at=(6, 0, 150))
    front.flag("4 FILLET ALL ROUND, GTAW", at=(-25, 0, -140), joint="weld")   # the seam's free side
    front.flag(f"ITEM {grease.number} ON ROD SEAL", at=(-27, 0, 13))

    # The section shows where the parts meet: each in one hatch, its neighbours
    # turned, the rod drawn uncut, and balloons saying which is which.
    cut = Sheet("A3", None, title=TITLE, subtitle="SECTION THROUGH THE DAMPER", part_number=NUMBER, revision="A",
                author="text-to-cad", stage="prototype", profile=GENERIC, notes=[EXAMPLE])
    side, right = cut.three_views(parts.assembly, views=("front", "right"))
    side.section("A", parts=parts)
    side.balloons(parts)
    side.flag("4 FILLET ALL ROUND, GTAW", at=(-25, 0, -140), joint="weld")
    side.flag(f"ITEM {locker.number} ON THREAD, TORQUE TO 25 NM", at=(6, 0, 150))
    cut.detail(side, (0, 0, 10), 22)
    sheets.insert(1, cut)

    # The eye's bushing bore: the fit the interview confirmed.
    eye = sheets.part("mounting_eye")
    eye_front = next(view for view in eye.views if view.name == "front")
    eye_front.hole((0, 0, -170), fit="H7")
    sheets.part("piston_rod").finish = "HARD CHROME PER AMS 2406"
    # The collar threads onto the tube: the thread the interview confirmed.
    collar = sheets.part("preload_adjuster_collar")
    collar_end = next(view for view in collar.views if view.name == "top")
    collar_end.hole((0, 0, PRELOAD_COLLAR_TOP_Z), thread=f"M{BODY_OD:g}x1.5 - 6H")
    tube_side, tube_end = (next(view for view in sheets.part("pressure_tube").views if view.name == name)
                           for name in ("front", "right"))
    r = BODY_OD / 2
    # The external thread: its length, said to be the thread's, and its designation
    # on the threaded stretch.
    tube_side.dim((r, 0, BODY_TOP_Z), (r, 0, BODY_TOP_Z - THREAD_LENGTH), text="<> THREAD LENGTH")
    tube_end.note(f"M{BODY_OD:g}x1.5 - 6g", (0, r, BODY_TOP_Z - THREAD_LENGTH / 2), offset=(15, 15))
    # The spring is drawn simplified: its data governs, and what is open is named.
    spring = sheets.part("coil_spring")
    spring_end = next(view for view in spring.views if view.name == "top")
    inner, outer = (SPRING_MEAN_D - SPRING_WIRE_D) / 2, (SPRING_MEAN_D + SPRING_WIRE_D) / 2
    top_z = SPRING_BOTTOM_Z + SPRING_HEIGHT
    spring_end.dim((inner, 0, top_z), (outer, 0, top_z), text="%%c<>")    # the wire, across the coil
    spring.notes = (*spring.notes,
                    "SIMPLIFIED REPRESENTATION: THE COIL IS DRAWN AS STRAIGHT SEGMENTS; THE SPRING DATA GOVERNS.",
                    f"SPRING DATA: WIRE ⌀{SPRING_WIRE_D:g}, MEAN COIL ⌀{SPRING_MEAN_D:g}, "
                    f"{SPRING_TURNS:g} COILS. FREE LENGTH, RATE AND END CONDITION NOT YET SPECIFIED.")
    for sheet in sheets:
        if EXAMPLE not in sheet.notes:
            sheet.notes = (*sheet.notes, EXAMPLE)
    return sheets


if __name__ == "__main__":
    motorcycle_shock_absorber_drawing()
