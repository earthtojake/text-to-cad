"""Locate confirmed native contacts in each component's rest frame for repair."""
import json
import sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from check_native_reported_contacts import native_shapes
from lib.layout import assembled_transforms
from lib.assembly import matrix_location
from lib.phalanx_r5_boolean import common

def main():
    diagnostic=json.loads((HERE/'native_reported_contacts.json').read_text())
    prior=json.loads((HERE/'final_rigid_delta_gate.json').read_text())
    revisions=prior['body_revisions']
    paths={digest:path for path,digest in prior['input_sha256'].items() if path.endswith('.step')}
    loaded={}
    def part(name):
        digest=revisions[name]['step_sha256']
        if digest not in loaded:
            print('LOAD',paths[digest],flush=True)
            bodies=native_shapes(paths[digest])
            expected={n for n,r in revisions.items() if r['step_sha256']==digest}
            if len(bodies)==len(expected)==1:bodies={next(iter(expected)):next(iter(bodies.values()))}
            loaded[digest]=bodies
        return loaded[digest][name]
    rows=[]
    for contact in diagnostic['rigid_contacts']:
        if not contact['native_collision']:continue
        a,b=contact['a'],contact['b'];sa,sb=part(a),part(b)
        fk=assembled_transforms(contact['pose'])
        fa,fb=revisions[a]['frame'],revisions[b]['frame']
        relative=np.linalg.inv(fk[fa])@fk[fb]
        hit=common(sa,matrix_location(relative)*sb)
        volume=sum(s.volume for s in hit.solids())
        box=hit.bounding_box()
        row={**contact,'a_frame':fa,'b_frame':fb,'a_volume_mm3':sa.volume,'b_volume_mm3':sb.volume,
             'a_rest_contact_bounds_mm':[tuple(box.min),tuple(box.max)],'local_common_mm3':volume}
        rows.append(row);print(json.dumps(row),flush=True)
        (HERE/'native_contact_regions.json').write_text(json.dumps({'complete':False,'rows':rows},indent=2)+'\n')
    (HERE/'native_contact_regions.json').write_text(json.dumps({'complete':True,'rows':rows},indent=2)+'\n')
if __name__=='__main__':main()
