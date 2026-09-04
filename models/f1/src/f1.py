"""F1 concept car — a modern ground-effect Formula 1 single-seater.

An original design. No team, livery, logo or sponsor marks. Three materials
only: carbon, exposed metal, and one vermillion accent.

Coordinates, package dimensions, suspension hardpoints, the DRS four-bar and
the material palette all live in `lib/spec.py`; the shared surface vocabulary
(airfoil family, blade family, body lofts) lives in `lib/surfaces.py`. Read
those two before changing anything here. Every child below is its own model
file under `src/` (`front_wing.py`, `corner_fl.py`, ...), built from `lib/`
and composed here by CALLING it.

--------------------------------------------------------------------------
OCCURRENCE ORDER IS FROZEN
--------------------------------------------------------------------------
The animation module (`f1.step.js`) addresses children as `#o1.N` in the
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
from cadgen import build123d as bd
from cadgen import step
from cadgen.assembly import AssemblyHelper

from airbox import airbox
from beam_wing import beam_wing
from cockpit import cockpit
from cooling import cooling
from corner_fl import corner_fl
from corner_fr import corner_fr
from corner_rl import corner_rl
from corner_rr import corner_rr
from details import details
from diffuser import diffuser
from drivetrain import drivetrain
from drs_actuator import drs_actuator
from drs_flap import drs_flap
from engine_cover import engine_cover
from floor import floor
from front_wing import front_wing
from halo import halo
from monocoque import monocoque
from nose import nose
from power_unit import power_unit
from rear_wing import rear_wing
from sidepod_left import sidepod_left
from sidepod_right import sidepod_right
from steering_rack import steering_rack
from suspension_front import suspension_front
from suspension_rear import suspension_rear
from track_rod_left import track_rod_left
from track_rod_right import track_rod_right


def assemble() -> bd.Compound:
    """Every child is a sibling MODEL under `src/`, added in the frozen order.

    Calling a model inside this body submits its build (if stale) to the pool
    and returns at once; the car links each child's tree, so a part edit is
    picked up by rerunning this script and nothing else is rebuilt.
    """
    asm = AssemblyHelper("f1_concept_car")
    asm.add(front_wing(), "front_wing")
    asm.add(nose(), "nose")
    asm.add(monocoque(), "monocoque")
    asm.add(halo(), "halo")
    asm.add(cockpit(), "cockpit")
    asm.add(sidepod_left(), "sidepod_left")
    asm.add(sidepod_right(), "sidepod_right")
    asm.add(engine_cover(), "engine_cover")
    asm.add(airbox(), "airbox")
    asm.add(floor(), "floor")
    asm.add(diffuser(), "diffuser")
    asm.add(cooling(), "cooling")
    asm.add(power_unit(), "power_unit")
    asm.add(drivetrain(), "drivetrain")
    asm.add(rear_wing(), "rear_wing")
    asm.add(drs_flap(), "drs_flap")
    asm.add(drs_actuator(), "drs_actuator")
    asm.add(beam_wing(), "beam_wing")
    asm.add(suspension_front(), "suspension_front")
    asm.add(suspension_rear(), "suspension_rear")
    asm.add(corner_fl(), "corner_fl")
    asm.add(corner_fr(), "corner_fr")
    asm.add(track_rod_left(), "track_rod_left")
    asm.add(track_rod_right(), "track_rod_right")
    asm.add(corner_rl(), "corner_rl")
    asm.add(corner_rr(), "corner_rr")
    asm.add(steering_rack(), "steering_rack")
    asm.add(details(), "details")
    return asm.build()


# No `kinematics=`: both of this car's mechanisms are CLOSED LOOPS. The DRS is
# a planar four-bar and the steering solves each wheel against a fixed-length
# track rod, and typed mates evaluate pure forward kinematics on a TREE — a
# loop needs a solver. Both solves therefore live in the animation module,
# which is Turing-complete by design and is where the teardown belongs anyway.
@step(out="../STEP/f1.step")
def f1():
    return assemble()


if __name__ == "__main__":
    f1()
