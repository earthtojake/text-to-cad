from cadgen import step
from lib.thumb_metacarpal import make_thumb_metacarpal

@step(out='../../STEP/anthropomorphic_hand/thumb_metacarpal_review.step')
def thumb_metacarpal_review():
    return make_thumb_metacarpal()

if __name__=='__main__':thumb_metacarpal_review()
