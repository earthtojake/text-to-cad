"""Resolved planetary reducer in assembly and a separated display."""
from cadgen import build123d as bd, step
from lib.gearbox import make_gearbox_parts
from lib.motor import make_motor_case,make_motor_endcap,make_motor_shaft

@step(out='../../STEP/anthropomorphic_hand/gearbox_review.step')
def gearbox_review():
    parts=make_gearbox_parts('assembled_gearbox')
    parts.extend([make_motor_case('assembled_motor_case'),make_motor_endcap('assembled_motor_endcap'),make_motor_shaft('assembled_motor_shaft')])
    assembled=[bd.Pos(-10,0,0)*p for p in parts]
    separated=make_gearbox_parts('separated_gearbox')
    offsets=[(0,0,12),(0,0,0),(0,0,0),(0,0,5),(0,0,16),(0,0,12),(0,0,0),(0,0,-5),(0,0,0),(0,0,-5),(0,0,0),(0,0,-5)]
    return bd.Compound(label='planetary_gearbox_family',children=assembled+[
        bd.Pos(12+x,y,z)*p for p,(x,y,z) in zip(separated,offsets)])

if __name__=='__main__': gearbox_review()
