"""F1 concept car — a modern ground-effect Formula 1 single-seater.

An original design. No team, livery, logo or sponsor marks. Three materials
only: carbon, exposed metal, and one vermillion accent.

Coordinates, package dimensions, suspension hardpoints, the DRS four-bar and
the material palette all live in `f1_parts/spec.py`; the shared surface
vocabulary (airfoil family, blade family, body lofts) lives in
`f1_parts/lib.py`. Read those two before changing anything here.

--------------------------------------------------------------------------
OCCURRENCE ORDER IS FROZEN
--------------------------------------------------------------------------
The animation module (`f1.anim.js`) addresses children as `#o1.N` in the
order below. Do not reorder, insert or remove a child without updating the
module's occurrence table in the same change.

  #o1.1   front_wing        #o1.15  rear_wing
  #o1.2   nose              #o1.16  drs_flap        <- rotates (DRS)
  #o1.3   monocoque         #o1.17  drs_actuator    <- four-bar (DRS)
  #o1.4   halo              #o1.18  beam_wing
  #o1.5   cockpit           #o1.19  suspension_front
  #o1.6   sidepod_left      #o1.20  suspension_rear
  #o1.7   sidepod_right     #o1.21  corner_fl       <- rotates (steering)
  #o1.8   engine_cover      #o1.22  corner_fr       <- rotates (steering)
  #o1.9   airbox            #o1.23  track_rod_left  <- re-aimed (steering)
  #o1.10  floor             #o1.24  track_rod_right <- re-aimed (steering)
  #o1.11  diffuser          #o1.25  corner_rl
  #o1.12  cooling           #o1.26  corner_rr
  #o1.13  power_unit        #o1.27  steering_rack   <- translates (steering)
  #o1.14  drivetrain        #o1.28  details
"""

from __future__ import annotations
from cadgen import step

from cadgen import build123d as bd

from cadgen.assembly import AssemblyHelper

from lib import (
    cockpit,
    details,
    drivetrain,
    engine_cover,
    floor,
    front_wing,
    monocoque,
    nose,
    power_unit,
    rear_wing,
    sidepods,
    suspension,
    wheels,
)


def assemble() -> bd.Compound:
    asm = AssemblyHelper("f1_concept_car")

    # --- front aero ------------------------------------------------------
    asm.add(front_wing.build_front_wing(), "front_wing")
    asm.add(nose.build_nose(), "nose")

    # --- survival cell / cockpit -----------------------------------------
    asm.add(monocoque.build_monocoque(), "monocoque")
    asm.add(monocoque.build_halo(), "halo")
    asm.add(cockpit.build_cockpit(), "cockpit")

    # --- bodywork panels (these lift away in the strip-down) --------------
    asm.add(sidepods.build_sidepod("left"), "sidepod_left")
    asm.add(sidepods.build_sidepod("right"), "sidepod_right")
    asm.add(engine_cover.build_engine_cover(), "engine_cover")
    asm.add(engine_cover.build_airbox(), "airbox")
    asm.add(floor.build_floor(), "floor")
    asm.add(floor.build_diffuser(), "diffuser")

    # --- power unit and drivetrain ---------------------------------------
    asm.add(sidepods.build_cooling(), "cooling")
    asm.add(power_unit.build_power_unit(), "power_unit")
    asm.add(drivetrain.build_drivetrain(), "drivetrain")

    # --- rear aero --------------------------------------------------------
    asm.add(rear_wing.build_rear_wing(), "rear_wing")
    asm.add(rear_wing.build_drs_flap(), "drs_flap")
    asm.add(rear_wing.build_drs_actuator(), "drs_actuator")
    asm.add(rear_wing.build_beam_wing(), "beam_wing")

    # --- suspension -------------------------------------------------------
    asm.add(suspension.build_suspension_front(), "suspension_front")
    asm.add(suspension.build_suspension_rear(), "suspension_rear")

    # --- corners (wheels, brakes, uprights) -------------------------------
    asm.add(wheels.build_corner("fl"), "corner_fl")
    asm.add(wheels.build_corner("fr"), "corner_fr")
    asm.add(suspension.build_track_rod("left"), "track_rod_left")
    asm.add(suspension.build_track_rod("right"), "track_rod_right")
    asm.add(wheels.build_corner("rl"), "corner_rl")
    asm.add(wheels.build_corner("rr"), "corner_rr")
    asm.add(suspension.build_steering_rack(), "steering_rack")

    # --- detail -----------------------------------------------------------
    asm.add(details.build_details(), "details")

    return asm.build()


# No `kinematics=`: both of this car's mechanisms are CLOSED LOOPS. The DRS is
# a planar four-bar and the steering solves each wheel against a fixed-length
# track rod, and typed mates evaluate pure forward kinematics on a TREE — a
# loop needs a solver. Both solves therefore live in the animation module,
# which is Turing-complete by design and is where the teardown belongs anyway.
@step(out="../STEP/f1.step", animation="f1.anim.js")
def f1():
    return assemble()


if __name__ == "__main__":
    f1()
