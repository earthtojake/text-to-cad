"""Exact mid-finger reaction comb and original skeletal rail mounting study."""
from cadgen import build123d as bd,step
from lib.guide_mounts import make_phalanx_comb
from lib.phalanx import make_phalanx
from lib.bowden_guide import make_bowden_body

@step(out='../../STEP/anthropomorphic_hand/guide_comb_review.step',mesh_tolerance=.001,mesh_angular_tolerance=.18)
def guide_comb_review():
    pieces=[make_phalanx(45,18,label='original_middle_proximal_frame')]
    pieces+=make_phalanx_comb(45,18,12.25,[-4.2,-3.,3.,4.2],'middle_mcp_outlet_comb')
    for lane in [-4.2,-3.,3.,4.2]:
        path=[{'kind':'bezier','points':[[lane,7,0],[lane,10,0],[lane,14,0],[lane,18,0]]}]
        pieces.append(make_bowden_body(path,f'lane_{lane}_liner',liner=True))
        pieces.append(make_bowden_body(path,f'lane_{lane}_tendon'))
    return bd.Compound(label='supported_split_reaction_comb_review',children=pieces)

if __name__=='__main__':guide_comb_review()
