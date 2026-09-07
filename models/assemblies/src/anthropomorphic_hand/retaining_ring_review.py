"""Isolated rings and paired in-groove fit examples, at real millimeter scale."""
from cadgen import build123d as bd, step
from lib.axle import make_axle
from lib.retaining_ring import make_retaining_ring


@step(out="../../STEP/anthropomorphic_hand/retaining_ring_review.step")
def retaining_ring_review():
    children=[]
    for radius, x, length in ((1.,-5.,3.5),(3.,5.,12.)):
        label="finger" if radius==1 else "wrist"
        ring=make_retaining_ring(radius,label=f"{label}_isolated_retaining_ring")
        children.append(bd.Pos(x,0,0)*ring)
        axle=make_axle(length,radius,label=f"{label}_fit_axle")
        seated=bd.Pos(0,0,length-.6)*make_retaining_ring(radius,label=f"{label}_seated_retaining_ring")
        overlap=axle.intersect(seated)
        if overlap is not None and sum(s.volume for s in overlap.solids())>1e-9:
            raise ValueError(f"{label}: retaining ring intersects axle")
        children.extend([bd.Pos(x,9,0)*axle,bd.Pos(x,9,0)*seated])
    return bd.Compound(label="retaining_ring_family_and_groove_fit", children=children)


if __name__=="__main__":retaining_ring_review()
