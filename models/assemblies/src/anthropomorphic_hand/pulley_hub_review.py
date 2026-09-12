"""Two separately resolved turned PIP hub-spacer bodies, assembled datums."""
from cadgen import build123d as bd,step
from lib.pulley_hub_extension import representative_bodies
@step(out='../../STEP/anthropomorphic_hand/pulley_hub_review.step')
def pulley_hub_review():
    return bd.Compound(label='middle_PIP_turned_hub_spacers',children=[b.shape for b in representative_bodies()])
if __name__=='__main__':pulley_hub_review()
