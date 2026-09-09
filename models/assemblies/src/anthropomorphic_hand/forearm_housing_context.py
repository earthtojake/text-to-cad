"""Open housing around the actual actuator pack and forearm guide banks."""
from pathlib import Path
from cadgen import build123d as bd,step,read_step
from lib.forearm_housing import forearm_housing_bodies
from lib.layout import TENDONS
from lib.motor import make_motor_case,make_motor_endcap,make_motor_shaft
from lib.capstan import make_capstan,make_terminal_ferrule
from lib.tension_cartridge import make_tension_cartridge
from lib.gearbox import make_gearbox_parts

@step(out='../../STEP/anthropomorphic_hand/forearm_housing_context.step')
def forearm_housing_context():
    parts=[s for s,*_ in forearm_housing_bodies()]
    root=Path(__file__).resolve().parents[2]/'STEP/anthropomorphic_hand'
    def leaves(n):return [s for c in n.children for s in leaves(c)] if n.children else [n]
    parts+=leaves(read_step(root/'forearm_mount_system_review.step'))
    parts+=leaves(read_step(root/'actuator_fasteners_review.step'))
    motor=[make_motor_case(),make_motor_endcap(),make_motor_shaft()]
    gear=make_gearbox_parts();cap=[make_capstan(),make_terminal_ferrule()]
    cartridge=make_tension_cartridge()
    for t in TENDONS:
        x,y,_=t['actuator_center'];sign=t['sign'];turn=bd.Rot(0,180 if sign<0 else 0,0)
        for i,p in enumerate(cartridge):
            s=bd.Pos(x,y,0)*turn*p;s.label=t['actuator']+f'_context_cartridge_{i}';parts.append(s)
        for i,p in enumerate(motor+gear):
            s=bd.Pos(x,y,sign*4)*turn*p;s.label=t['actuator']+f'_context_motor_gear_{i}';parts.append(s)
        for i,p in enumerate(cap):
            s=bd.Pos(x,y,sign*4)*turn*bd.Pos(0,0,29)*p;s.label=t['actuator']+f'_context_capstan_{i}';parts.append(s)
    return bd.Compound(label='open_forearm_housing_actual_actuator_context',children=parts)

if __name__=='__main__':forearm_housing_context()
