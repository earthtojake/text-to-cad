"""Compare repaired bridge material and datums against the native prior export.

Both directed native Boolean differences must be empty. This is a geometry
equivalence check; strict self-intersection validation is a separate gate.
"""
import json
import numpy as np
from pathlib import Path
from check_native_reported_contacts import native_shapes,sha,HERE
from lib.phalanx_r5_boolean import cut

def main():
    folder=HERE.parents[1]/'STEP/anthropomorphic_hand'
    old_path=folder/'fingertip_pad_export_repair.step';new_path=folder/'fingertip_bridge_repair_review.step'
    inputs={str(p):sha(p) for p in (Path(__file__),old_path,new_path,HERE/'check_native_reported_contacts.py',HERE.parents[1]/'src/anthropomorphic_hand/lib/phalanx_r5_boolean.py')}
    old=native_shapes(old_path);new=native_shapes(new_path);assert len(new)==5 and set(new)<=set(old)
    rows=[]
    for name,b in sorted(new.items()):
        a=old[name];assert len(a.solids())==len(b.solids())==1 and a.is_valid and b.is_valid
        ab=cut(a,b);ba=cut(b,a);abox=a.bounding_box();bbox=b.bounding_box()
        bounds_error=float(np.max(np.abs(np.array([tuple(abox.min),tuple(abox.max)])-np.array([tuple(bbox.min),tuple(bbox.max)]))))
        row=dict(body=name,old_volume_mm3=a.volume,new_volume_mm3=b.volume,old_minus_new_solids=len(ab.solids()),new_minus_old_solids=len(ba.solids()),old_minus_new_faces=len(ab.faces()),new_minus_old_faces=len(ba.faces()),old_minus_new_mm3=sum(s.volume for s in ab.solids()),new_minus_old_mm3=sum(s.volume for s in ba.solids()),maximum_bounds_error_mm=bounds_error,pass_=not ab.faces() and not ba.faces() and bounds_error<1e-5)
        rows.append(row);print('BRIDGE EQUIVALENCE',row,flush=True)
    changed=[p for p,h in inputs.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=inputs,rows=rows,changed_during_audit=changed,complete=not changed,pass_=not changed and all(r['pass_'] for r in rows));report['pass']=report.pop('pass_')
    (HERE/'fingertip_bridge_equivalence.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']
if __name__=='__main__':main()
