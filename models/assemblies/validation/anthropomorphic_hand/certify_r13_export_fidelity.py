"""Bind R13 export QA from strict validity, boundary records and fresh deltas.

This does not assert exact source/export material equality: the failed Boolean
identity diagnostic is preserved separately. 3166 occurrences have completed
zero-face directed native differences. The remaining 47 rigid occurrences are
checked directly from the final export at every static pose. For 46 variable
tendon occurrences, complete native surface/edge/vertex/oriented-trim records
agree within 1e-10 in their stored field units, allowing integer native periods.
That scalar precision check is not represented as a global Hausdorff bound.
Every exported occurrence also passes the strict native every-placement gate.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    inputs = {str(Path(__file__)): sha(__file__)}

    def read(name, passing=True):
        path = HERE/name
        doc = json.loads(path.read_text())
        assert doc['complete'] and not doc.get('changed_during_audit'), name
        if passing:
            assert doc.get('pass', doc.get('pass_', doc.get('ok', False))), name
        inputs[str(path)] = sha(path)
        for p, h in doc['input_sha256'].items():
            assert sha(p) == h and (p not in inputs or inputs[p] == h), p
            inputs[p] = h
        return doc

    strict = read('native_r13_strict_gate.json')
    records = read('native_r13_export_records.json', passing=False)
    fork = read('native_r13_export_fork_gate.json')
    delta = read('native_r13_export_rigid_delta_gate.json')
    metadata_path = HERE/'mechanical_candidate_r13_frames.json'
    metadata = {r['name']: r for r in json.loads(metadata_path.read_text())}
    inputs[str(metadata_path)] = sha(metadata_path)
    assert strict['occurrenceCount'] == len(metadata) == records['occurrence_count'] == 3259
    assert strict['failureCount'] == 0 and strict['selfIntersectionCheck'] == 'every-placement'
    document = HERE.parents[1]/'STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step'
    digest = sha(document)
    assert inputs[str(document)] == records['document_sha256'] == fork['document_sha256'] == delta['document_sha256'] == digest
    changed = set(fork['changed_names']) | set(delta['changed_names'])
    assert len(changed) == 47 and not set(fork['changed_names']) & set(delta['changed_names'])
    assert all(metadata[n]['frame'] != 'variable' for n in changed)
    maps = [{r['sample']: r for r in doc['rows']} for doc in (fork, delta)]
    assert len(maps[0]) == len(maps[1]) == 225 and set(maps[0]) == set(maps[1])
    for name in maps[0]:
        a, b = [m[name] for m in maps]
        assert a['pose'] == b['pose'] and a['pass_'] and b['pass_']
        assert not a['collisions'] and not b['collisions']
        assert a['routes']['pass'] and b['routes']['pass']
    rows = []
    numeric_variables = []
    for proof in records['rows']:
        for name in proof['members']:
            if proof['status'] == 'completed_zero_face_native_differences':
                native = proof['native_boolean_result']
                assert native['pass_'] and native['added_faces'] == native['removed_faces'] == 0
                method = 'completed_native_material_equality'
            elif name in changed:
                method = 'fresh_final_export_rigid_and_route_delta_225_poses'
            else:
                assert metadata[name]['frame'] == 'variable' and metadata[name]['kind'] == 'tendon', name
                assert proof['status'] == 'native_boundary_records_agree' and proof['agrees']
                assert proof['epsilon'] == 1e-10 and proof['maximum_scalar_difference'] <= 1e-10
                reverse = proof['reverse_comparison']
                assert reverse['agrees'] and reverse['maximum_scalar_difference'] <= 1e-10
                method = 'strict_native_tendon_with_complete_boundary_record_concordance'
                numeric_variables.append(name)
            rows.append(dict(body=name, proof_representative=proof['body'], method=method))
    assert len(rows) == len({r['body'] for r in rows}) == 3259
    assert len(numeric_variables) == 46
    assert {r['body'] for r in rows} == set(metadata)
    assert {r['body'] for r in rows if r['method'].startswith('fresh_')} == changed
    modified = [p for p, h in inputs.items() if sha(p) != h]
    assert not modified
    report = dict(scope=__doc__, input_sha256=inputs, document_sha256=digest,
                  occurrence_count=3259, direct_export_rigid_delta_count=47,
                  numeric_variable_tendon_count=46, sample_count=225,
                  numeric_variable_tendons=sorted(numeric_variables), rows=rows,
                  static_poses=[dict(sample=n, pose=maps[0][n]['pose']) for n in sorted(maps[0])],
                  exact_material_equality_certified=False,
                  global_spatial_error_bound_certified=False,
                  changed_during_audit=[], complete=True, pass_=True)
    (HERE/'native_r13_export_fidelity_gate.json').write_text(json.dumps(report, indent=2)+'\n')
    print('R13 EXPORT QA PASS; exact Boolean equality remains a separate failed diagnostic')


if __name__ == '__main__':
    main()
