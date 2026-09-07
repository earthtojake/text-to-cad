"""Strict native R13 validity by exact placed-payload reuse and fresh checks.

Requires the complete R11 every-placement audit, byte-identical placed BREP
payloads for every inherited occurrence, and the bound native strict run for
every other occurrence. An incomplete baseline can never produce a pass.
"""
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    files={name:HERE/name for name in ('native_r13_validity_reuse_plan.json',
           'mechanical_candidate_r11_strict.json','native_r13_fresh_strict.json',
           'native_r13_fresh_strict_binding.json')}
    docs={name:json.loads(path.read_text()) for name,path in files.items()}
    plan=docs['native_r13_validity_reuse_plan.json']
    baseline=docs['mechanical_candidate_r11_strict.json']
    fresh=docs['native_r13_fresh_strict.json']
    binding=docs['native_r13_fresh_strict_binding.json']
    assert baseline['ok'] and not baseline.get('partial',False), 'Complete baseline strict audit required'
    assert fresh['ok'] and not fresh.get('partial',False)
    assert baseline['selfIntersectionCheck']==fresh['selfIntersectionCheck']=='every-placement'
    assert not baseline['errors'] and not fresh['errors'] and baseline['failureCount']==fresh['failureCount']==0
    assert baseline['occurrenceCount']==plan['old_occurrence_count']==3257
    identical,new=set(plan['byte_identical_names']),set(plan['fresh_names'])
    assert not identical&new and identical|new==set(plan['new'])
    assert plan['new_occurrence_count']==len(plan['new'])==3259
    assert len(new)==fresh['occurrenceCount']==29
    assert binding['names']==plan['fresh_names'] and binding['refs']==plan['fresh_refs']
    assert all(plan['new'][n]['placed_brep_sha256']==plan['old'][n]['placed_brep_sha256'] for n in identical)
    inputs={str(path):sha(path) for path in [Path(__file__),*files.values()]}
    for document in (plan,binding):
        for p,h in document['input_sha256'].items():
            assert sha(p)==h,p
            inputs[p]=h
    result=dict(scope=__doc__,input_sha256=inputs,occurrenceCount=3259,
                inherited_occurrence_count=len(identical),fresh_occurrence_count=len(new),
                selfIntersectionCheck='every-placement',failureCount=0,complete=True,ok=True)
    (HERE/'native_r13_strict_gate.json').write_text(json.dumps(result,indent=2)+'\n')
    print('R13 NATIVE STRICT PASS',len(identical),'exact inherited /',len(new),'fresh')


if __name__=='__main__':
    main()
