"""Every actual hand phalanx, in five rows from index through thumb."""
from cadgen import build123d as bd, step
from lib.phalanx import make_phalanx
from lib.layout import FINGERS

@step(out='../../STEP/anthropomorphic_hand/phalanx_variants_review.step',
      mesh_tolerance=.003,mesh_angular_tolerance=.012)
def phalanx_variants_review():
    children=[]
    variants=[(f.name,f.lengths,f.widths) for f in FINGERS]
    variants.append(('thumb',(36.,27.,21.),(19.,16.,13.)))
    for row,(name,lengths,widths) in enumerate(variants):
        for column,(length,width) in enumerate(zip(lengths,widths)):
            label=f'{name}_{("proximal","middle","distal")[column]}_frame'
            frame=make_phalanx(length,width,column==2,label)
            children.append(bd.Pos(row*25,column*60,0)*frame)
    return bd.Compound(label='all_actual_phalanx_variants',children=children)

if __name__=='__main__':
    phalanx_variants_review()
