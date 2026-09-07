from cadgen import build123d as bd,step
from lib.capstan import make_capstan,make_terminal_ferrule,make_stored_tendon

@step(out='../../STEP/anthropomorphic_hand/capstan_review.step')
def capstan_review():
    return bd.Compound(label='six_turn_storage_capstan_review',children=[make_capstan(),make_terminal_ferrule(),make_stored_tendon()])
if __name__=='__main__':capstan_review()
