"""Individually removable open forearm side frames and wiring hardware."""
from cadgen import build123d as bd,step
from lib.forearm_housing import forearm_housing_bodies

@step(out='../../STEP/anthropomorphic_hand/forearm_housing_review.step')
def forearm_housing_review():
    return bd.Compound(label='forearm_open_housing_and_wiring_provisions',children=[s for s,*_ in forearm_housing_bodies()])

if __name__=='__main__':forearm_housing_review()
