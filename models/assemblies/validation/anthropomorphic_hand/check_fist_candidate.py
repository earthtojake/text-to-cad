"""Compare fist candidates against the known fifth-ray contacts only."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from lib.assembly import matrix_location
from lib.layout import assembled_transforms,FINGERS
from lib.phalanx_r5_boolean import common
from check_native_reported_contacts import native_shapes
from check_pad_export_roundtrip import volume

def main():
    inputs_manifest=HERE/'rigid_clearance_inputs.json'
    manifest=json.loads(inputs_manifest.read_text());step=Path(manifest['step'])
    assert hashlib.sha256(step.read_bytes()).hexdigest()==manifest['step_sha256']
    shapes=native_shapes(step);frames={n:r['frame'] for n,r in manifest['bodies'].items()}
    pads=step.parent.parent/'fingertip_pad_export_repair.step'
    shapes.update(native_shapes(pads))
    pad_frames=HERE/'fingertip_pad_export_repair_frames.json'
    frames.update({r['name']:r['frame'] for r in json.loads(pad_frames.read_text())})
    contacts_path=HERE/'native_contact_regions.json';contacts=json.loads(contacts_path.read_text())['rows']
    pairs=[r for r in contacts if r['sample']=='full_fist_candidate']
    original=pairs[0]['pose'];assert pairs
    report={'scope':__doc__,'input_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (step,pads,pad_frames,inputs_manifest,contacts_path,Path(__file__))},'candidates':[]}
    for label,angles in [('maximum_joint_angles',(90,110,80)),('anatomical_fist',(90,90,60))]:
        pose=dict(original)
        for f in FINGERS:
            pose.update({f.name+'_mcp_flexion':angles[0],f.name+'_pip':angles[1],f.name+'_dip':angles[2]})
        fk=assembled_transforms(pose);rows=[]
        for pair in pairs:
            a,b=pair['a'],pair['b']
            relative=np.linalg.inv(fk[frames[a]])@fk[frames[b]]
            sa=shapes[a];sb=matrix_location(relative)*shapes[b]
            v=volume(common(sa,sb))[0];gap=sa.distance_to(sb)
            row=dict(a=a,b=b,intersection_mm3=v,gap_mm=gap,pass_=v<1e-7)
            rows.append(row);print(label,json.dumps(row),flush=True)
        report['candidates'].append(dict(label=label,pose=pose,pairs=rows,known_contact_pairs_pass=all(r['pass_'] for r in rows)))
    (HERE/'fist_native_candidate_check.json').write_text(json.dumps(report,indent=2)+'\n')
    final=report['candidates'][-1]
    if final['known_contact_pairs_pass']:
        (HERE/'final_fist_candidate.json').write_text(json.dumps({'label':final['label'],'pose':final['pose'],'scope':'Candidate only. Known fifth-ray contacts pass; full assembly and tendon checks still required. Every independent joint limit is unchanged.','rejected_maximum_angle_fist':original},indent=2)+'\n')
    assert final['known_contact_pairs_pass']

if __name__=='__main__':main()
