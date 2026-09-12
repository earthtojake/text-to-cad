"""One actual actuator mount, with hardware seated in its structural context."""
from pathlib import Path
import sys
SRC=Path(__file__).resolve().parents[2]/'src/anthropomorphic_hand'
sys.path.insert(0,str(SRC))
from cadgen import step,build123d as bd
from lib.actuator_fasteners import actuator_fasteners
from lib.motor import make_motor_case,make_motor_endcap,make_motor_shaft
from lib.gearbox import make_gearbox_housing,make_gearbox_spindle
from lib.tension_cartridge import make_tension_cartridge

@step(out='../../STEP/anthropomorphic_hand/actuator_fasteners_macro.step')
def actuator_fasteners_macro():
    hardware=[bd.Pos(27,252,0)*p for p,*_ in actuator_fasteners()[:16]]
    parts=make_tension_cartridge()+[bd.Pos(0,0,4)*f() for f in (make_motor_case,make_motor_endcap,make_motor_shaft,make_gearbox_housing,make_gearbox_spindle)]
    # Matching local section of the actual annular frame seat, same dimensions
    # and all six staggered reamed bores as the full chassis.
    from math import radians,sin,cos
    seat=bd.Cylinder(8.7,.7)-bd.Cylinder(6.9,1)
    seat=bd.fillet(seat.edges(),.055)
    for a in range(0,360,60):seat=seat-bd.Pos(7.55*cos(radians(a)),7.55*sin(radians(a)),0)*bd.Cylinder(.54,1.2)
    from lib.finish import finish
    parts.append(finish(seat,'dark','local_chassis_mounting_annulus'))
    cap=bd.import_step(SRC.parents[1]/'STEP/anthropomorphic_hand/capstan_review.step')
    parts.extend(bd.Pos(0,0,33)*c for c in cap.children)
    return bd.Compound(label='actual_actuator_fastener_stack_macro',children=parts+hardware)

if __name__=='__main__':actuator_fasteners_macro()
