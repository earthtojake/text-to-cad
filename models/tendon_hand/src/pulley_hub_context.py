"""Representative collars in the frozen, material-restored 3151-body context."""
from cadgen import step
from lib.assembly import Body,compound
from lib.native_integration import frozen_bodies
from lib.palette import ASSEMBLY_MATERIALS
from lib.braided_presentation import braided_presentation
from lib.pulley_hub_extension import representative_bodies
from phalanx_beauty_review import replacements
ANIMATION = braided_presentation()


@step(out='../STEP/pulley_hub_context.step', animation=ANIMATION, materials=ASSEMBLY_MATERIALS)
def pulley_hub_context():
    repl=replacements();old=frozen_bodies()
    parts=[Body(repl.get(body.name,body.shape),body.frame,body.system,body.kind) for body in old]
    assert len(parts)==3151
    parts.extend(representative_bodies())
    return compound(parts,'middle_PIP_hub_collar_representative_full_hand')
if __name__=='__main__':pulley_hub_context()
