"""Representative collars in the frozen, material-restored 3151-body context."""
import json
from pathlib import Path
from cadgen import build123d as bd,step
from phalanx_beauty_review import base_bodies,replacements
from lib.pulley_hub_extension import representative_bodies
@step(out='../../STEP/anthropomorphic_hand/pulley_hub_context.step')
def pulley_hub_context():
    repl=replacements();parts=[repl.get(s.label,s) for s in base_bodies()]
    styles=json.loads((Path(__file__).resolve().parents[2]/'validation/anthropomorphic_hand/integration_native_base_appearance.json').read_text())['occurrences']
    assert len(parts)==3151
    for s in parts:
        row=styles[s.label]
        if row.get('color') is not None:s.color=tuple(row['color'])
        s.cad_material=dict(row['material'])
    parts.extend(b.shape for b in representative_bodies())
    return bd.Compound(label='middle_PIP_hub_collar_representative_full_hand',children=parts)
if __name__=='__main__':pulley_hub_context()
