"""Verify the repaired bank's native attachment chain to the wrist cradle."""
import json
from pathlib import Path
from check_native_reported_contacts import native_shapes,sha,HERE

CHAIN=['thumb_radial_shared_guide_bank_structural','palm_metacarpal_truss',
       'palm_wrist_radial_0p4mm_seat_spacer','palm_wrist_radial_M3_flanged_thread_insert',
       'wrist_palm_cradle']

def main():
    gatepath=HERE/'native_reroute_supports_r10_gate.json';gate=json.loads(gatepath.read_text())
    assert gate['complete'] and not gate['changed_during_audit']
    sources={h:Path(p) for p,h in gate['input_sha256'].items() if p.endswith('.step')}
    inputs={str(Path(__file__)):sha(__file__),str(gatepath):sha(gatepath)};parts={}
    for name in CHAIN:
        rev=gate['body_revisions'][name];assert rev['frame']=='wrist_flexion'
        path=HERE.parents[1]/'STEP/anthropomorphic_hand/radial_bank_screw_clearance_candidate.step' if name==CHAIN[0] else sources[rev['step_sha256']]
        if name!=CHAIN[0]:assert sha(path)==rev['step_sha256']
        inputs[str(path)]=sha(path);native=native_shapes(path)
        if name not in native:
            assert len(native)==1,(name,list(native));native={name:next(iter(native.values()))}
        parts[name]=native[name]
    rows=[]
    for a,b in zip(CHAIN,CHAIN[1:]):
        aa,bb=parts[a].solids(),parts[b].solids();assert len(aa)==len(bb)==1
        gap=aa[0].distance_to(bb[0]);rows.append(dict(a=a,b=b,gap_mm=gap,pass_=gap<=.025))
        print('BANK ATTACHMENT',a,b,gap,flush=True)
    changed=[p for p,h in inputs.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=inputs,chain=CHAIN,rows=rows,frame='wrist_flexion',contact_tolerance_mm=.025,changed_during_audit=changed,complete=not changed,pass_=not changed and all(r['pass_'] for r in rows))
    report['pass']=report.pop('pass_');(HERE/'radial_bank_attachment_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
if __name__=='__main__':main()
