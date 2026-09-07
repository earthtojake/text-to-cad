"""All60 native bridge/mount pairs, plus five retained pad bond contacts."""
import json
from pathlib import Path
from check_native_reported_contacts import native_shapes,sha,HERE
from lib.phalanx_r5_boolean import common

def main():
    folder=HERE.parents[1]/'STEP/anthropomorphic_hand'
    files=[folder/n for n in ['fingertip_bridge_repair_review.step','fingertip_pad_export_repair.step','fingernail_export_repair_review.step','phalanx_beauty_review.step']]
    bridge,pads,nails,hosts=[native_shapes(p) for p in files]
    parts={**pads,**nails,**hosts};parts.update(bridge)
    inputs={str(p):sha(p) for p in [*files,Path(__file__),HERE/'check_native_reported_contacts.py',HERE.parents[1]/'src/anthropomorphic_hand/lib/phalanx_r5_boolean.py']}
    rows=[];bonds=[]
    for name,a in sorted(bridge.items()):
        finger=name.split('_')[0];others={n:p for n,p in parts.items() if n.startswith(finger+'_') and (n in pads or n in nails or n==finger+'_distal_frame') and n!=name}
        assert len(others)==12,(finger,len(others))
        for other,b in others.items():
            hit=common(a,b);v=sum(s.volume for s in hit.solids());rows.append(dict(bridge=name,other=other,intersection_mm3=v,pass_=v<1e-7))
        gap=a.solids()[0].distance_to(pads[finger+'_fingertip_silicone_pad'].solids()[0]);bonds.append(dict(finger=finger,gap_mm=gap,pass_=gap<1e-5))
        print('BRIDGE FIT',finger,all(r['pass_'] for r in rows),gap,flush=True)
    assert len(rows)==60
    changed=[p for p,h in inputs.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=inputs,pairs=rows,bond_contacts=bonds,complete=not changed,changed_during_audit=changed,pass_=not changed and all(r['pass_'] for r in rows+bonds));report['pass']=report.pop('pass_')
    (HERE/'fingertip_bridge_fit_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
if __name__=='__main__':main()
