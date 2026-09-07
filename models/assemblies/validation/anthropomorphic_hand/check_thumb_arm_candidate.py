"""Focused native thumb-arm interfaces and reported neighbours across CMC yaw.

This diagnoses a candidate before the all-neighbour225-pose rigid/tendon gates.
The native arm, unchanged bore datums, seven known obstacles and palm are tested.
"""
import argparse,gzip,json
from pathlib import Path
import numpy as np
from check_native_reported_contacts import native_shapes,sha,HERE
from cadgen import build123d as bd
from lib.assembly import matrix_location
from lib.layout import assembled_transforms,THUMB_CMC
from lib.phalanx_r5_boolean import common
from lib.finger_routing import transform_path
from lib.transport_guide import path_wire
from check_hand_route_pairs import group_radius
from path_solid_clearance import boundary_separation

NAME='thumb_cmc_negative_yaw_outlet_structural_jaw_1'
OTHERS=['thumb_cmc_abduction_negative_drive_pulley','thumb_cmc_abduction_positive_drive_pulley',
        'thumb_cmc_flexion_negative_drive_pulley','thumb_cmc_fixed_flex_shared_structural',
        'thumb_cmc_parent_inlet_comb_structural_jaw','thumb_cmc_fixed_flex_-1_host_cap',
        'thumb_cmc_fixed_flex_-1_host_M0p6_screw','palm_metacarpal_truss']

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--step',default=str(HERE.parents[1]/'STEP/anthropomorphic_hand/thumb_reaction_arm_context_candidate.step'));parser.add_argument('--prefix',default='thumb_arm_candidate');args=parser.parse_args()
    folder=HERE.parents[1]/'STEP/anthropomorphic_hand';path=Path(args.step).resolve()
    registry_path=HERE/'final_rigid_delta_gate.json';registry=json.loads(registry_path.read_text())
    inputs={str(p):sha(p) for p in (Path(__file__),path,registry_path)}
    revisions=registry['body_revisions'];sources={h:Path(p) for p,h in registry['input_sha256'].items() if p.endswith('.step')}
    parts={};frames={n:revisions[n]['frame'] for n in OTHERS+[NAME]}
    for digest in {revisions[n]['step_sha256'] for n in OTHERS if n!='palm_metacarpal_truss'}:
        source=sources[digest];assert sha(source)==digest;inputs[str(source)]=digest
        native=native_shapes(source)
        parts.update({n:s for n,s in native.items() if n in OTHERS})
    support=folder/'static_clearance_relief_review.step';inputs[str(support)]=sha(support)
    parts.update({n:s for n,s in native_shapes(support).items() if n in OTHERS})
    jaw=native_shapes(path)[NAME];assert len(jaw.solids())==1 and jaw.is_valid
    parts[NAME]=jaw;assert set(parts)==set(OTHERS+[NAME])
    base=bd.Pos(*THUMB_CMC)*bd.Rot(0,0,45)
    bores=[]
    for x,y,z,r in [(-.9,-3.275,-7.95,.22),(0,-3.5,-15.2,.32),(0,3.5,-15.2,.32)]:
        tool=base*bd.Pos(x,y,z)*bd.Cylinder(r,3,rotation=(0,90,0));hit=common(jaw,tool)
        v=sum(s.volume for s in hit.solids());bores.append(dict(center=[x,y,z],radius=r,intersection_mm3=v,pass_=v<1e-7))
    manifest_path=HERE/'final_static_route_packet_manifest.json';manifest=json.loads(manifest_path.read_text());inputs[str(manifest_path)]=sha(manifest_path)
    samples=[r for r in manifest['rows'] if r['label']=='flat_open' or r['label'].startswith('thumb_cmc_abduction_')]
    assert len(samples)==10 and {r['pose'].get('thumb_cmc_abduction',0.) for r in samples}=={-25.,-15.,-5.,0.,5.,15.,25.,35.,45.}
    rows=[]
    for sample in samples:
        fk=assembled_transforms(sample['pose']);placed=matrix_location(fk[frames[NAME]])*jaw
        collisions=[]
        for name in OTHERS:
            hit=common(placed,matrix_location(fk[frames[name]])*parts[name]);v=sum(s.volume for s in hit.solids())
            if v>1e-7:collisions.append(dict(body=name,intersection_mm3=v))
        packet_path=Path(sample['file']);assert sha(packet_path)==sample['file_sha256'];inputs[str(packet_path)]=sha(packet_path)
        packet=json.loads(gzip.decompress(packet_path.read_bytes()));assert packet['source_sha256']==sample['source_sha256']
        route=next(r for r in packet['routes'] if r['name']=='thumb_cmc_flexion_negative')
        group=next(g for g in route['groups'] if g['label']=='thumb_cmc_flexion_negative_cmc_yaw_reaction')
        wire=path_wire(transform_path(group['path'],np.linalg.inv(fk[frames[NAME]])))
        distance=wire.distance_to(jaw.solids()[0]);radius=group_radius(group)
        proof=boundary_separation(wire,jaw.solids()[0],radius) if distance<radius-1e-6 else None
        route_pass=distance>=radius-1e-6 or bool(proof and proof['proven_separated'])
        row=dict(sample=sample['label'],pose=sample['pose'],collisions=collisions,tendon_centerline_gap_mm=distance,tendon_radius_mm=radius,boundary_proof=proof,pass_=not collisions and route_pass)
        rows.append(row);print('CMC ARM',row,flush=True)
    changed=[p for p,h in inputs.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=inputs,bores=bores,rows=rows,complete=not changed,changed_during_audit=changed,pass_=not changed and all(r['pass_'] for r in rows+bores));report['pass']=report.pop('pass_')
    (HERE/f'{args.prefix}_gate.json').write_text(json.dumps(report,indent=2)+'\n');assert report['pass']

if __name__=='__main__':main()
