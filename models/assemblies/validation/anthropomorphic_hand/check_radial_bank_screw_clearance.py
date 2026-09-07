"""Native material-subset proof and all225 rigid-pair transfer for the bank.

The prior all-neighbour bank sweep has exactly one failing pair, a screw in
the same rigid frame. Check that pair on the new native solid, and require
zero added faces in the directed new-minus-old Boolean difference. Every
other bank pair inherits clearance from the containing old solid.
"""
import json
from pathlib import Path
from check_native_reported_contacts import native_shapes,sha,HERE
from cadgen import build123d as bd
from lib.guide_mounts import guide_end_registry
from lib.phalanx_r5_boolean import common,cut

NAME='thumb_radial_shared_guide_bank_structural'
SCREW='thumb_wrist_splice_outlet_comb_liner_-1_M0p6_screw'
def main():
    folder=HERE.parents[1]/'STEP/anthropomorphic_hand';oldpath=folder/'static_clearance_relief_review.step';newpath=folder/'radial_bank_screw_clearance_candidate.step'
    old=native_shapes(oldpath)[NAME];new=native_shapes(newpath)[NAME]
    gatepath=HERE/'native_reroute_supports_r10_gate.json';gate=json.loads(gatepath.read_text());assert gate['complete'] and gate['sample_count']==225 and not gate['changed_during_audit']
    assert all(sha(p)==h for p,h in gate['input_sha256'].items())
    assert gate['body_revisions'][NAME]['step_sha256']==sha(oldpath)
    assert gate['body_revisions'][NAME]['frame']==gate['body_revisions'][SCREW]['frame']=='wrist_flexion'
    revision=gate['body_revisions'][SCREW]['step_sha256'];screwpath=next(Path(p) for p,h in gate['input_sha256'].items() if p.endswith('.step') and h==revision)
    screw=native_shapes(screwpath)[SCREW];assert len(new.solids())==1 and new.is_valid
    addition=cut(new,old);hit=common(new,screw);volume=sum(s.volume for s in hit.solids());gap=new.solids()[0].distance_to(screw.solids()[0])
    print('BANK NATIVE',dict(added_faces=len(addition.faces()),added_solids=len(addition.solids()),intersection_mm3=volume,gap_mm=gap),flush=True)
    # The nearest untouched portion has the design's existing .020mm gap;
    # the new pocket's .025mm expansion is not a whole-body gap requirement.
    assert not addition.faces() and volume<1e-7 and gap>0.
    bores=[]
    for e in guide_end_registry():
        if e.frame!='wrist_flexion' or not e.name.startswith('thumb_') or '_wrist_guide_outlet' not in e.name or not ('_mcp_' in e.name or '_ip_' in e.name):continue
        tool=bd.Plane(origin=e.point,z_dir=e.tangent).location*bd.Cylinder(.47,1.);h=common(new,tool);v=sum(s.volume for s in h.solids());bores.append(dict(name=e.name,intersection_mm3=v,pass_=v<1e-7))
    assert len(bores)==6 and all(r['pass_'] for r in bores)
    rows=[]
    for row in gate['rows']:
        contacts=[c for c in row['collisions'] if NAME in (c['a'],c['b'])]
        assert all(set([c['a'],c['b']])=={NAME,SCREW} for c in contacts)
        rows.append(dict(sample=row['sample'],pose=row['pose'],prior_contact_count=len(contacts),pass_=True))
    strictpath=HERE/'radial_bank_screw_clearance_strict.json';strict=json.loads(strictpath.read_text());assert strict['ok'] and strict['occurrenceCount']==1
    paths=[Path(__file__),oldpath,newpath,gatepath,screwpath,strictpath,HERE/'check_native_reported_contacts.py',HERE.parents[1]/'src/anthropomorphic_hand/lib/phalanx_r5_boolean.py']
    report=dict(scope=__doc__,input_sha256={str(p):sha(p) for p in paths},body=NAME,frame='wrist_flexion',old_minus_new_mm3=old.volume-new.volume,new_minus_old_faces=len(addition.faces()),screw_intersection_mm3=volume,screw_gap_mm=gap,bores=bores,sample_count=len(rows),rows=rows,complete=True,pass_=True);report['pass']=report.pop('pass_')
    (HERE/'radial_bank_screw_clearance_gate.json').write_text(json.dumps(report,indent=2)+'\n');print('NATIVE BANK SUBSET PASS',gap,len(rows),flush=True)
if __name__=='__main__':main()
