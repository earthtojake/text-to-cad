"""The exact 48 forearm mounting cartridge placements, for strict validation."""
from cadgen import build123d as bd,step
from lib.tension_cartridge import make_tension_cartridge

@step(out='../../STEP/anthropomorphic_hand/tension_cartridge_bank_review.step')
def tension_cartridge_bank_review():
    prototype=make_tension_cartridge()
    bodies=[]
    for row,y in enumerate((-252,-211,-170,-129,-88,-47)):
        for col,x in enumerate((-27,-9,9,27)):
            for bank,rotation in (('palmar',0),('dorsal',180)):
                placement=bd.Pos(x,y,0)*bd.Rot(0,rotation,0)
                for i,body in enumerate(prototype):
                    placed=placement*body
                    placed.label=f'{bank}_station_{row+1}_{col+1}_{"spring" if i==0 else "bonded_gauge_"+str(i)}'
                    bodies.append(placed)
    return bd.Compound(label='all_48_tension_cartridges',children=bodies)

if __name__=='__main__':
    tension_cartridge_bank_review()
