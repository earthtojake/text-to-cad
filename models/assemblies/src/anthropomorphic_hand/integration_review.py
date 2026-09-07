"""Assembly integration study. Missing systems are explicitly tracked in GAUNTLET.md."""
from cadgen import step
from lib.assembly import integration_bodies,compound


@step(out='../../STEP/anthropomorphic_hand/integration_review.step')
def integration_review():
    return compound(integration_bodies())


if __name__=='__main__': integration_review()
