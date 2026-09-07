"""A single cartridge shown upright and inverted to expose its three sensors."""
from cadgen import build123d as bd,step
from lib.tension_cartridge import make_tension_cartridge

@step(out='../../STEP/anthropomorphic_hand/tension_cartridge_review.step')
def tension_cartridge_review():
    bodies=[]
    for prefix,x,rot in (('upper',-10,0),('underside',10,180)):
        bodies.extend(bd.Pos(x,0,0)*bd.Rot(rot,0,0)*s for s in make_tension_cartridge(prefix))
    return bd.Compound(label='torsional_tendon_load_cartridge_review',children=bodies)

if __name__=='__main__':
    tension_cartridge_review()
