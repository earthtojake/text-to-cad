"""Four refined phalanges in the frozen complete hand; all routing unchanged."""
import json
from pathlib import Path
from cadgen import build123d as bd,step
from phalanx_beauty_review import base_bodies,replacements
@step(out='../../STEP/anthropomorphic_hand/phalanx_sculpt_representative_context.step')
def phalanx_sculpt_representative_context():
    repl=replacements();old=base_bodies()
    from cadgen import read_step
    from lib.layout import FINGERS,finger_fan_matrix
    from lib.assembly import matrix_location
    from lib.finish import finish
    f=FINGERS[1]
    s=read_step(Path(__file__).resolve().parents[2]/'STEP/anthropomorphic_hand/phalanx_sculpt_early_probe_r4.step')
    repl['middle_proximal_frame']=finish(matrix_location(finger_fan_matrix(f))*bd.Pos(f.x,f.base_y,0)*s,'aluminum','middle_proximal_frame')
    assert len([s for s in old if s.label in repl])==4
    appearance=Path(__file__).resolve().parents[2]/'validation/anthropomorphic_hand/integration_native_base_appearance.json'
    materials=json.loads(appearance.read_text())['occurrences']
    parts=[repl.get(s.label,s) for s in old]
    assert len(parts)==3151
    for part in parts:
        row=materials[part.label]
        if row.get('color') is not None:part.color=tuple(row['color'])
        part.cad_material=dict(row['material'])
    return bd.Compound(label='refined_skeletal_phalanges_in_complete_hand_context',children=parts)
if __name__=='__main__':phalanx_sculpt_representative_context()
