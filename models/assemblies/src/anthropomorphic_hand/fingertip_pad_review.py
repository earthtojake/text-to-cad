"""Five mounted pads at real scale, plus an isolated index pad macro specimen."""
from cadgen import build123d as bd, step
from lib.fingertip_pad import make_fingertip_pad
from lib.phalanx import make_phalanx
from lib.layout import FINGERS

@step(out='../../STEP/anthropomorphic_hand/fingertip_pad_review.step',
      mesh_tolerance=.001,mesh_angular_tolerance=.01)
def fingertip_pad_review():
    parts=[]
    variants=[(f.name,f.lengths[2],f.widths[2]) for f in FINGERS]+[('thumb',21.,13.)]
    for i,(name,length,width) in enumerate(variants):
        place=bd.Pos(i*18,0,0)
        parts.append(place*make_phalanx(length,width,True,name+'_distal_frame'))
        parts.extend(place*p for p in make_fingertip_pad(name,length,width))
    return bd.Compound(label='five_anatomical_fingertip_pad_mounts',children=parts)

if __name__=='__main__':fingertip_pad_review()
