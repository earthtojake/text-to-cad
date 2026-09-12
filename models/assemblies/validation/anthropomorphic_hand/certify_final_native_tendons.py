"""Bind the repaired 225-pose tendon proof to the complete R13 native export.

The R6 arm is a proved subset of the already cleared R5 arm. The continuous
phalanx, its supports and two new collars have a joint all-48-route audit.
Every unchanged body revision and every final exported frame must match.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    inputs = {str(Path(__file__)):sha(__file__)}

    def read(name):
        path = HERE/name
        report = json.loads(path.read_text())
        assert report['complete'] and report['pass'] and not report.get('changed_during_audit',[])
        for p,h in report['input_sha256'].items():
            assert sha(p) == h,p
            assert p not in inputs or inputs[p] == h,p
            inputs[p] = h
        inputs[str(path)] = sha(path)
        return report

    old = read('all_native_repaired_tendon_solids_gate.json')
    arm = read('thumb_arm_r6_subset_gate.json')
    finger = read('native_finger_finish_r5_v2_gate.json')
    revisions = {n:dict(r) for n,r in old['body_revisions'].items()}
    assert arm['new_minus_old_faces'] == 0 and revisions[arm['body']]['step_sha256'] == arm['old_step_sha256']
    assert revisions[arm['body']]['frame'] == arm['frame']
    # Finger audit context must match every old body it retained.
    removed = set(finger['removed_names'])
    new_names = set(finger['changed_names'])
    assert len(removed) == 33 and len(new_names) == 35
    assert removed <= set(revisions)
    for name,revision in revisions.items():
        if name not in removed:
            assert finger['body_revisions'][name] == revision,name
    revisions[arm['body']]['step_sha256'] = arm['new_step_sha256']
    revisions = {n:r for n,r in revisions.items() if n not in removed}
    assert not new_names & set(revisions)
    revisions.update({n:finger['body_revisions'][n] for n in new_names})
    assert len(revisions) == 3041
    folder = HERE.parents[1]/'STEP/anthropomorphic_hand'
    document = folder/'hand_mechanical_candidate_r13.step'
    buildpath = HERE/'mechanical_candidate_r13_build_inputs.json'
    framespath = HERE/'mechanical_candidate_r13_frames.json'
    build = json.loads(buildpath.read_text())
    frames = json.loads(framespath.read_text())
    assert len(frames) == 3259 and sum(r['frame']=='variable' for r in frames)==218
    exported = {r['name']:build['body_revisions'][r['name']] for r in frames if r['frame']!='variable'}
    assert exported == revisions, [(n,r,exported.get(n)) for n,r in revisions.items() if exported.get(n)!=r]
    for p,h in build['input_sha256'].items():
        assert sha(p)==h,p
        inputs[p]=h
    for p in (document,buildpath,framespath):
        inputs[str(p)]=sha(p)
    previous = {r['sample']:r for r in old['rows']}
    rows = []
    assert len(finger['rows'])==len(previous)==225
    for row in finger['rows']:
        prior = previous[row['sample']]
        assert prior['pose']==row['pose']
        assert prior['pass_'] and row['routes']['pass'] and not row['routes']['collisions']
        names = {r['tendon'] for r in prior['tendon_table']}
        assert len(names)==48 and names=={r['tendon'] for r in row['routes']['tendon_table']}
        rows.append(dict(sample=row['sample'],pose=row['pose'],tendon_count=48,body_count=3041,collisions=[],pass_=True))
    changed = [p for p,h in inputs.items() if sha(p)!=h]
    report = dict(scope=__doc__,input_sha256=inputs,body_revisions=revisions,rows=rows,
                  sample_count=225,tendon_count=48,body_count=3041,document_sha256=sha(document),
                  changed_during_audit=changed,complete=not changed,pass_=not changed)
    report['pass']=report.pop('pass_')
    (HERE/'native_r13_tendon_gate.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R13 NATIVE TENDONS',report['pass'],'225 poses / 48 routes / 3041 rigid bodies')
    assert report['pass']


if __name__=='__main__':
    main()
