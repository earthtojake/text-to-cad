"""Four refined phalanges in the frozen complete hand; all routing unchanged."""
from pathlib import Path
from cadgen import build123d as bd,step
from lib.native_integration import frozen_bodies
from lib.palette import ASSEMBLY_MATERIALS
from lib.braided_presentation import braided_presentation
from phalanx_beauty_review import replacements
ANIMATION = braided_presentation()


@step(out='../STEP/phalanx_sculpt_representative_context.step', animation=ANIMATION, materials=ASSEMBLY_MATERIALS)
def phalanx_sculpt_representative_context():
    repl=replacements();old=frozen_bodies()
    from cadgen import read_step
    from lib.layout import FINGERS,finger_fan_matrix
    from lib.assembly import Body,compound,matrix_location
    from lib.finish import finish
    f=FINGERS[1]
    s=read_step(Path(__file__).resolve().parents[1]/'STEP/phalanx_sculpt_early_probe_r4.step')
    repl['middle_proximal_frame']=finish(matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y,0)*s,'aluminum','middle_proximal_frame')
    assert len([body for body in old if body.name in repl])==4
    parts=[Body(repl.get(body.name,body.shape),body.frame,body.system,body.kind) for body in old]
    assert len(parts)==3151
    return compound(parts,'refined_skeletal_phalanges_in_complete_hand_context')
if __name__=='__main__':phalanx_sculpt_representative_context()
