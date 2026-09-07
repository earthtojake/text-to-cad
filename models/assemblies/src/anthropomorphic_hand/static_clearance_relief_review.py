"""Local clearance candidate, awaiting complete hand acceptance."""
from cadgen import build123d as bd,step
from lib.static_clearance_relief import make_reliefs
@step(out='../../STEP/anthropomorphic_hand/static_clearance_relief_review.step')
def static_clearance_relief_review():
    return bd.Compound(label='machined_clearance_candidate',children=make_reliefs())
if __name__=='__main__':static_clearance_relief_review()
