"""Actual assembled terminal fingers: host, palmar pad, dorsal nail, hardware."""
from cadgen import build123d as bd,step
from lib.fingernail import fingernail_bodies
from lib.fingertip_pad import fingertip_pad_bodies
from lib.phalanx import make_phalanx
from lib.layout import FINGERS,THUMB_CMC,THUMB_LENGTHS,finger_fan_matrix
from lib.assembly import matrix_location

@step(out='../../STEP/anthropomorphic_hand/fingernail_review.step',mesh_tolerance=.003,mesh_angular_tolerance=.03)
def fingernail_review():
    parts=[p for p,f,s,k in fingernail_bodies()]+[p for p,f,s,k in fingertip_pad_bodies()]
    for finger in FINGERS:
        for i,(length,width) in enumerate(zip(finger.lengths,finger.widths)):
            place=matrix_location(finger_fan_matrix(finger))*bd.Pos(finger.x,finger.base_y+sum(finger.lengths[:i]),0)
            parts.append(place*make_phalanx(length,width,i==2,finger.name+'_'+('proximal','middle','distal')[i]+'_frame'))
    for i in (1,2):
        place=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)*bd.Pos(0,sum(THUMB_LENGTHS[:i]),0)
        parts.append(place*make_phalanx(THUMB_LENGTHS[i],(19,16,13)[i],i==2,'thumb_'+('metacarpal','proximal','distal')[i]+'_frame'))
    return bd.Compound(label='five_fingernails_in_anatomical_hand_context',children=parts)

if __name__=='__main__':fingernail_review()
