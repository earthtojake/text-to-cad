"""Certify the complete native R13 export for the specified 225 static poses.

This joins strict export validity, native export fidelity and fresh export deltas,
hand-frame and physically actuated rigid pairs, all tendon/rigid pairs, curve
constraints, payout conservation and the neutral virtual-work matrix. It does
not confer aesthetic acceptance or certify unauthored pose/explode transitions.
The export-fidelity certificate distinguishes completed native material equality,
direct final-export rigid checks and variable-tendon boundary-record agreement;
it does not assert exact global source/export material equality.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    files = {
        'strict': 'native_r13_strict_gate.json',
        'export': 'native_r13_export_fidelity_gate.json',
        'rigid': 'native_r13_hand_rigid_gate.json',
        'payout_rigid': 'native_r13_payout_rigid_gate.json',
        'tendons': 'native_r13_tendon_gate.json',
        'curves': 'payout_static_curves_gate.json',
        'payout': 'final_static_actuator_payout.json',
        'moments': 'native_r13_neutral_moment_arm_gate.json',
    }
    inputs = {str(Path(__file__)): sha(__file__)}
    docs = {}
    for key,name in files.items():
        path = HERE/name
        doc = docs[key] = json.loads(path.read_text())
        assert doc['complete'] and not doc.get('partial') and not doc.get('changed_during_audit'), name
        assert doc.get('pass',doc.get('pass_',doc.get('ok',False))), name
        inputs[str(path)] = sha(path)
        for p,h in doc['input_sha256'].items():
            assert sha(p)==h and (p not in inputs or inputs[p]==h), p
            inputs[p] = h
    strict = docs['strict']
    assert strict['occurrenceCount']==3259 and strict['failureCount']==0
    assert strict['selfIntersectionCheck']=='every-placement'
    export = docs['export']
    assert export['occurrence_count']==len(export['rows'])==3259
    assert len({r['body'] for r in export['rows']})==3259
    assert export['direct_export_rigid_delta_count']==47
    assert export['numeric_variable_tendon_count']==46
    document = HERE.parents[1]/'STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step'
    document_hash = sha(document)
    assert str(document) in inputs and inputs[str(document)]==document_hash
    rigid = docs['rigid']
    assert len(rigid['body_revisions'])==3041
    for key in ('rigid','payout_rigid','tendons'):
        doc = docs[key]
        assert doc['document_sha256']==document_hash and doc['body_revisions']==rigid['body_revisions']
    maps = {key:{r['sample']:r for r in docs[key]['rows']}
            for key in ('rigid','payout_rigid','tendons','curves','payout')}
    samples = set(maps['rigid'])
    assert len(samples)==225 and all(set(rows)==samples for rows in maps.values())
    export_poses = {r['sample']:r['pose'] for r in export['static_poses']}
    assert set(export_poses)==samples
    for name in samples:
        rows = [mapping[name] for mapping in maps.values()]
        assert all(r['pose']==rows[0]['pose'] and r.get('pass',r.get('pass_',True)) for r in rows)
        assert all(not maps[k][name]['collisions'] for k in ('rigid','payout_rigid','tendons'))
        assert export_poses[name]==rows[0]['pose']
    assert docs['moments']['joint_count']==24 and docs['moments']['tendon_count']==48
    changed = [p for p,h in inputs.items() if sha(p)!=h]
    assert not changed
    report = dict(scope=__doc__,input_sha256=inputs,document_sha256=document_hash,
                  occurrence_count=3259,rigid_body_count=3041,variable_body_count=218,
                  tendon_count=48,actuator_count=48,joint_count=24,sample_count=225,
                  rows=[dict(sample=n,pose=maps['rigid'][n]['pose'],pass_=True) for n in sorted(samples)],
                  complete=True,static_mechanics_pass=True,whole_model_accepted=False,
                  export_exact_material_equality_certified=False,
                  export_fidelity_method='completed native differences, fresh direct export deltas and complete variable-tendon native boundary records',
                  remaining=['independent visual acceptance','whole-hand acceptance',
                             'pose choreography and 0.02 sampling','staged explode and 0.05 sampling',
                             'checked Viewer with both parameters'])
    (HERE/'native_r13_static_mechanical_gate.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R13 STATIC MECHANICS PASS: 3259 occurrences / 225 poses; later milestones remain open')


if __name__ == '__main__':
    main()
