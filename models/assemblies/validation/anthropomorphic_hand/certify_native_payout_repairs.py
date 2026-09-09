"""Bind the completed physical-actuator rigid audit and repair deltas to R13.

The baseline covers all moving actuator endpoints. Seven mechanical repairs
and 35 finger/collar occurrences have separate native separation proofs at the
same 225 payout poses. Hand-frame pairs and strict export validity are separate.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    inputs = {str(Path(__file__)): sha(__file__)}

    def read(name):
        path = HERE/name
        doc = json.loads(path.read_text())
        assert doc['complete'] and doc['pass'] and not doc.get('changed_during_audit'), name
        inputs[str(path)] = sha(path)
        for p,h in doc['input_sha256'].items():
            assert sha(p)==h and (p not in inputs or inputs[p]==h), p
            inputs[p] = h
        return doc

    base = read('native_payout_rigid_grouped_gate.json')
    repairs = read('repair_payout_separation_gate.json')
    finger = read('native_finger_finish_r5_v2_gate.json')
    hand = read('native_r13_hand_rigid_gate.json')
    assert base['full_static_coverage'] and base['sample_count']==225
    revisions = {n:dict(r) for n,r in base['body_revisions'].items()}
    assert len(revisions)==3039
    changed = set(repairs['body_revisions'])
    removed = set(finger['removed_names'])
    added = set(finger['changed_names'])
    assert len(changed)==7 and len(removed)==33 and len(added)==35
    assert changed <= set(revisions) and removed <= set(revisions)
    assert not changed & (removed|added)
    for n in changed:
        assert revisions[n]['frame']==repairs['body_revisions'][n]['frame'], n
        revisions[n] = repairs['body_revisions'][n]
    for n in removed:
        del revisions[n]
    assert not added & set(revisions)
    revisions.update({n:finger['body_revisions'][n] for n in added})
    assert len(revisions)==3041 and revisions==hand['body_revisions']
    for n,r in finger['body_revisions'].items():
        if n not in changed:
            assert revisions[n]==r, n
    maps = [{r['sample']:r for r in doc['rows']} for doc in (base,repairs,finger,hand)]
    assert all(len(rows)==225 and set(rows)==set(maps[0]) for rows in maps)
    rows = []
    for name in sorted(maps[0]):
        original, repaired, revised, static = [mapping[name] for mapping in maps]
        assert original['complete'] and original['pass'] and not original['collisions']
        assert repaired['pass_'] and revised['pass_'] and static['pass_']
        assert original['pose']==repaired['pose']==revised['pose']==static['pose']
        active = set(original['moving_bodies'])
        assert active <= set(revisions) and not active & (changed|added)
        assert all(base['body_revisions'][n]==revisions[n] for n in active)
        assert repaired['pair_count']==len(active)*7 and not repaired['unresolved_native_pairs']
        assert revised['payout_aabb_pairs']==len(active)*35
        rows.append(dict(sample=name,pose=original['pose'],moving_body_count=len(active),
                         moving_bodies=sorted(active),body_count=3041,collisions=[],pass_=True))
    document = HERE.parents[1]/'STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step'
    assert sha(document)==hand['document_sha256']
    inputs[str(document)] = sha(document)
    changed_inputs = [p for p,h in inputs.items() if sha(p)!=h]
    report = dict(scope=__doc__,input_sha256=inputs,body_revisions=revisions,
                  document_sha256=sha(document),rows=rows,sample_count=225,body_count=3041,
                  changed_during_audit=changed_inputs,complete=not changed_inputs)
    report['pass'] = report['complete']
    (HERE/'native_r13_payout_rigid_gate.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['pass']
    print('R13 PHYSICAL ACTUATOR RIGIDS PASS: 225 poses / 3041 rigid bodies')


if __name__ == '__main__':
    main()
