import json
from pathlib import Path
from cadgen import build123d as bd,step
from phalanx_beauty_review import base_bodies,replacements
from phalanx_continuous_representative_r5 import candidate_bodies
@step(out='../../STEP/anthropomorphic_hand/phalanx_continuous_context_r5.step')
def phalanx_continuous_context_r5():
    old=base_bodies();repl=replacements();new=candidate_bodies();repl.update({s.label:s for s in new})
    prefixes=('middle_mcp_outlet_comb','middle_pip_inlet_comb','middle_pip_drive_guide')
    removed=[s for s in old if s.label=='middle_proximal_frame' or s.label.startswith(prefixes)]
    removed_names={s.label for s in removed}
    retained=[s for s in old if s.label not in removed_names]
    materials=json.loads((Path(__file__).resolve().parents[2]/'validation/anthropomorphic_hand/integration_native_base_appearance.json').read_text())['occurrences']
    parts=[repl.get(s.label,s) for s in retained]+new
    assert len(parts)==3151-len(removed)+len(new)
    for part in parts:
        key=part.label
        if key not in materials:
            stem=key.rsplit('_',1)[0] if key.rsplit('_',1)[-1].isdigit() else key
            matches=sorted(k for k in materials if k==stem or k.startswith(stem+'_'))
            assert matches,(key,'no corresponding original finish');key=matches[0]
        row=materials[key]
        if row.get('color') is not None:part.color=tuple(row['color'])
        part.cad_material=dict(row['material'])
    return bd.Compound(label='continuous_skeletal_rail_in_complete_hand',children=parts)
if __name__=='__main__':phalanx_continuous_context_r5()
