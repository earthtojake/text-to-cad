"""Four refined phalanges in the frozen complete hand; all routing unchanged."""
import json
from pathlib import Path
from cadgen import build123d as bd,step
from phalanx_beauty_review import base_bodies,replacements
@step(out='../../STEP/anthropomorphic_hand/phalanx_beauty_context.step')
def phalanx_beauty_context():
    repl=replacements();old=base_bodies()
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
if __name__=='__main__':phalanx_beauty_context()
