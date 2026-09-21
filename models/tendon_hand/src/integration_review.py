"""Assembly integration study. Missing systems are explicitly tracked in GAUNTLET.md."""
from cadgen import step
from lib.assembly import integration_bodies,compound
from lib.palette import RIGID_ASSEMBLY_MATERIALS


@step(out='../STEP/integration_review.step', materials=RIGID_ASSEMBLY_MATERIALS)
def integration_review():
    return compound(integration_bodies())


if __name__=='__main__': integration_review()
