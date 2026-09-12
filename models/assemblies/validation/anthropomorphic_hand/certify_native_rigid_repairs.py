"""Complete hand-frame rigid clearance for the R13 mechanical candidate.

The retained and replacement gates cover every original pair. The two thumb
repairs have a complete neighbour audit plus the R6 native subset/cap proof.
Bridge material equivalence and the fresh finger-family delta close the final
replacement set. Physical actuator payout and strict export validity are
separate certificates, required before whole-model acceptance.
"""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    inputs={str(Path(__file__)):sha(__file__)}

    def read(name, passing=True):
        path=HERE/name
        d=json.loads(path.read_text())
        assert d['complete'] and not d.get('changed_during_audit',[]) and not d.get('invalidated',False),name
        if passing:
            assert d['pass'],name
        for p,h in d['input_sha256'].items():
            assert sha(p)==h,p
            assert p not in inputs or inputs[p]==h,p
            inputs[p]=h
        inputs[str(path)]=sha(path)
        return d

    retained=read('native_retained_final_gate.json')
    replacement=read('native_replacement_final_gate.json',False)
    reroute=read('native_reroute_supports_r5_gate.json',False)
    subset=read('thumb_arm_r6_subset_gate.json')
    bridges=read('fingertip_bridge_equivalence.json')
    finger=read('native_finger_finish_r5_v2_gate.json')
    baseline=replacement['body_revisions']
    assert len(baseline)==3039
    kept=set(replacement['retained_names'])
    changed=set(replacement['changed_names'])
    assert not kept & changed and kept | changed == set(baseline)
    assert len(kept)==2594 and len(changed)==445
    assert kept==set(retained['body_revisions'])
    assert all(retained['body_revisions'][n]==baseline[n] for n in kept)
    targets=set(reroute['changed_names'])
    assert targets=={'thumb_cmc_negative_yaw_outlet_structural_jaw_1','thumb_radial_shared_guide_bank_structural'}
    assert set(reroute['body_revisions'])==set(baseline)
    for name, revision in baseline.items():
        if name not in targets:
            assert reroute['body_revisions'][name]==revision,name
    revisions={n:dict(r) for n,r in reroute['body_revisions'].items()}
    assert subset['new_minus_old_faces']==0
    assert revisions[subset['body']]['step_sha256']==subset['old_step_sha256']
    revisions[subset['body']]['step_sha256']=subset['new_step_sha256']
    folder=HERE.parents[1]/'STEP/anthropomorphic_hand'
    old_bridge=folder/'fingertip_pad_export_repair.step'
    new_bridge=folder/'fingertip_bridge_repair_review.step'
    assert len(bridges['rows'])==5
    for row in bridges['rows']:
        assert row['old_minus_new_faces']==row['new_minus_old_faces']==0 and row['pass_']
        assert revisions[row['body']]['step_sha256']==bridges['input_sha256'][str(old_bridge)]
        revisions[row['body']]['step_sha256']=bridges['input_sha256'][str(new_bridge)]
    removed,new_names=set(finger['removed_names']),set(finger['changed_names'])
    assert len(removed)==33 and len(new_names)==35 and removed<=set(revisions)
    for name, revision in revisions.items():
        if name not in removed and name!=subset['body']:
            assert finger['body_revisions'][name]==revision,name
    assert finger['body_revisions'][subset['body']]['step_sha256']==subset['old_step_sha256']
    revisions={n:r for n,r in revisions.items() if n not in removed}
    assert not set(revisions)&new_names
    revisions.update({n:finger['body_revisions'][n] for n in new_names})
    assert len(revisions)==3041
    tables=[{r['sample']:r for r in d['rows']} for d in (retained,replacement,reroute,subset,finger)]
    labels=set(tables[0])
    assert len(labels)==225 and all(set(t)==labels for t in tables)
    rows=[]
    for label in sorted(labels):
        a,b,c,d,e=[t[label] for t in tables]
        assert a['pose']==b['pose']==c['pose']==d['pose']==e['pose']
        assert a['pass'] and not a['collisions']
        assert set(b['pair_scope']['any_endpoint_in'])==changed
        assert all({hit['a'],hit['b']} & targets for hit in b['collisions'])
        assert set(c['pair_scope']['any_endpoint_in'])==targets
        assert all({hit['a'],hit['b']}=={subset['body'],'thumb_cmc_yaw_drive_-1_host_cap'} for hit in c['collisions'])
        assert d['pass_'] and e['rigid']['pass'] and not e['rigid']['collisions']
        assert set(e['rigid']['pair_scope']['any_endpoint_in'])==new_names
        rows.append(dict(sample=label,pose=a['pose'],body_count=3041,collisions=[],pass_=True))
    buildpath=HERE/'mechanical_candidate_r13_build_inputs.json'
    framespath=HERE/'mechanical_candidate_r13_frames.json'
    build=json.loads(buildpath.read_text())
    frames=json.loads(framespath.read_text())
    exported={r['name']:build['body_revisions'][r['name']] for r in frames if r['frame']!='variable'}
    assert exported==revisions
    for p,h in build['input_sha256'].items():
        assert sha(p)==h,p
        inputs[p]=h
    document=folder/'hand_mechanical_candidate_r13.step'
    inputs.update({str(p):sha(p) for p in (document,buildpath,framespath)})
    changed_inputs=[p for p,h in inputs.items() if sha(p)!=h]
    report=dict(scope=__doc__,input_sha256=inputs,body_revisions=revisions,rows=rows,sample_count=225,
                body_count=3041,document_sha256=sha(document),changed_during_audit=changed_inputs,
                complete=not changed_inputs,pass_=not changed_inputs)
    report['pass']=report.pop('pass_')
    (HERE/'native_r13_hand_rigid_gate.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R13 HAND RIGIDS',report['pass'],'225 poses / 3041 native bodies')
    assert report['pass']


if __name__=='__main__':
    main()
