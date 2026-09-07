"""Resolve the two newly discovered index/thumb contacts in the fist candidate."""
import hashlib,json,sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'src/anthropomorphic_hand'))
from cadgen import build123d as bd
from cadgen.step_export import export_build123d_step_file
from check_native_reported_contacts import native_shapes
from lib.layout import assembled_transforms
from lib.assembly import matrix_location
from lib.phalanx_r5_boolean import common

PAIRS=[('index_distal_frame','thumb_mcp_ip_outlet_comb_structural_lower_jaw'),('index_fingernail_conformal_saddle','thumb_proximal_frame')]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    history_path=HERE/'final_rigid_delta_gate.json';history=json.loads(history_path.read_text())
    names={n for pair in PAIRS for n in pair};records={n:history['body_revisions'][n] for n in names}
    sources={h:Path(p) for p,h in history['input_sha256'].items() if p.endswith('.step')}
    folder=HERE.parents[1]/'STEP/anthropomorphic_hand/imported'
    subset=folder/'fist_contact_inputs.step';proof=HERE/'fist_contact_inputs.json'
    if not subset.exists():
        parts={};inputs={str(history_path):sha(history_path)}
        for digest in {r['step_sha256'] for r in records.values()}:
            p=sources[digest];assert sha(p)==digest;inputs[str(p)]=digest
            print('LOAD',p,flush=True);loaded=native_shapes(p)
            parts.update({n:loaded[n] for n,r in records.items() if r['step_sha256']==digest})
        export_build123d_step_file(bd.Compound(label='native_fist_contact_inputs',children=[parts[n] for n in sorted(parts)]),subset)
        proof.write_text(json.dumps({'input_sha256':inputs,'step_sha256':sha(subset),'bodies':records},indent=2)+'\n')
    saved=json.loads(proof.read_text());assert sha(subset)==saved['step_sha256']
    shapes=native_shapes(subset);candidate_path=HERE/'final_fist_candidate.json';candidate=json.loads(candidate_path.read_text())
    rows=[]
    for q,yaw,cmc in [(60.,-10.,-25.),(65.,-10.,-25.),(55.,-10.,-25.),(60.,-10.,-15.),(65.,-10.,-15.),(55.,-10.,-15.),(70.,-15.,-20.),(70.,5.,-20.),(70.,15.,-20.)]:
        pose={**candidate['pose'],'thumb_mcp_flexion':q,'thumb_mcp_abduction':yaw,'thumb_cmc_abduction':cmc};fk=assembled_transforms(pose);pairs=[]
        for a,b in PAIRS:
            relative=np.linalg.inv(fk[records[a]['frame']])@fk[records[b]['frame']]
            result=common(shapes[a],matrix_location(relative)*shapes[b]);v=result.volume if result.solids() else 0.
            pairs.append(dict(a=a,b=b,intersection_mm3=v,pass_=v<1e-7))
        row={'thumb_mcp_flexion':q,'thumb_mcp_abduction':yaw,'thumb_cmc_abduction':cmc,'pose':pose,'pairs':pairs,'known_pairs_pass':all(p['pass_'] for p in pairs)};rows.append(row);print(json.dumps(row),flush=True)
    report={'scope':__doc__,'input_sha256':{str(p):sha(p) for p in (history_path,subset,proof,candidate_path,Path(__file__))},'rows':rows}
    (HERE/'fist_thumb_variant_check.json').write_text(json.dumps(report,indent=2)+'\n')
    clear=[r for r in rows if r['known_pairs_pass']]
    if clear:
        chosen=clear[0]
        (HERE/'fist_thumb_variant_candidate.json').write_text(json.dumps({'label':candidate['label'],'pose':chosen['pose'],'scope':'Candidate only; clears the two known index/thumb contacts. Requires new full route and rigid checks.','predecessor_pose':candidate['pose']},indent=2)+'\n')
    assert clear

if __name__=='__main__':main()
