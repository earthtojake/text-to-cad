"""Four refined phalanges in the frozen complete hand; all routing unchanged."""
from cadgen import step
from lib.assembly import Body, compound
from lib.native_integration import frozen_bodies
from lib.palette import ASSEMBLY_MATERIALS
from lib.braided_presentation import braided_presentation
from phalanx_beauty_review import replacements
ANIMATION = braided_presentation()


@step(out='../STEP/phalanx_beauty_context.step', animation=ANIMATION, materials=ASSEMBLY_MATERIALS)
def phalanx_beauty_context():
    repl=replacements();old=frozen_bodies()
    assert len([body for body in old if body.name in repl])==4
    parts=[Body(repl.get(body.name,body.shape),body.frame,body.system,body.kind) for body in old]
    assert len(parts)==3151
    return compound(parts,'refined_skeletal_phalanges_in_complete_hand_context')
if __name__=='__main__':phalanx_beauty_context()
