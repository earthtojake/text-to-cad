"""Record complete source/export evidence without claiming Boolean equality.

Completed zero-face native Boolean results retain their original meaning.
For failed or unfinished Boolean classes, independently compare all native
boundary records. A numeric record match is reported as such, not relabelled
as exact material equality. Any mismatching body remains explicitly unresolved.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from cadgen import build123d as bd
from cadgen._internal import surface_extract
from check_native_reported_contacts import native_shapes
from native_boundary_records import compare

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    checkpoint_path = HERE/'native_r13_export_material_stopped_partial.json'
    build_path = HERE/'mechanical_candidate_r13_build_inputs.json'
    document = HERE.parents[1]/'STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step'
    baseline = json.loads(checkpoint_path.read_text())
    build = json.loads(build_path.read_text())
    paths = [Path(__file__), HERE/'native_boundary_records.py',
             Path(surface_extract.__file__), checkpoint_path, build_path, document]
    inputs = {str(p): sha(p) for p in paths}
    for p, h in baseline['input_sha256'].items():
        assert sha(p) == h and (p not in inputs or inputs[p] == h), p
        inputs[p] = h
    groups = baseline['proof_members']
    names = [n for group in groups for n in group]
    assert len(groups) == 1230 and len(names) == len(set(names)) == 3259
    assert set(names) == set(build['body_revisions'])
    completed = {r['body']: r for r in baseline['group_rows']}
    assert len(completed) == len(baseline['group_rows']) == 1229
    assert set(completed) <= {g[0] for g in groups}
    selected = [g for g in groups if g[0] not in completed or not completed[g[0]]['pass_']]
    assert len(selected) == 73
    native = native_shapes(document)
    assert set(native) == set(names)
    sources = {digest: Path(path) for path, digest in build['input_sha256'].items()}
    loaded = {}

    def source(name):
        digest = build['body_revisions'][name]['step_sha256']
        path = sources[digest]
        if digest not in loaded:
            assert sha(path) == digest
            loaded[digest] = native_shapes(path)
        shapes = loaded[digest]
        if name not in shapes and len(shapes) == 1:
            return next(iter(shapes.values()))
        return shapes[name]

    control_shape = source('index_dip_negative_drive_terminal_ferrule')
    reversed_shape = deepcopy(control_shape)
    reversed_shape.wrapped.Reverse()
    controls = {
        'native_clone': compare(control_shape, deepcopy(control_shape)),
        'translated_1e-8_mm': compare(control_shape, bd.Pos(1e-8, 0, 0)*control_shape),
        'translated_0p01_mm': compare(control_shape, bd.Pos(.01, 0, 0)*control_shape),
        'rotated_0p01_deg': compare(control_shape, bd.Rot(0, 0, .01)*control_shape),
        'reversed_orientation': compare(control_shape, reversed_shape),
    }
    assert controls['native_clone']['agrees']
    assert all(not r['agrees'] for n, r in controls.items() if n != 'native_clone')
    rows = []
    report = dict(scope=__doc__, input_sha256=inputs, document_sha256=sha(document),
                  complete=False, expected_occurrence_count=3259,
                  expected_proof_class_count=1230, controls=controls, rows=rows,
                  exact_material_equality_certified=False,
                  spatial_error_bound_certified=False,
                  collision_clearance_certified=False)
    out = HERE/'native_r13_export_records.json'

    def save():
        temp = out.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2)+'\n')
        temp.replace(out)

    for group in groups:
        name = group[0]
        old = completed.get(name)
        if old is not None and old['pass_']:
            assert old['added_faces'] == old['removed_faces'] == 0
            result = dict(status='completed_zero_face_native_differences',
                          native_boolean_result=old)
        else:
            result = compare(source(name), native[name])
            result['status'] = 'native_boundary_records_agree' if result['agrees'] else 'unresolved_boundary_records'
            result['native_boolean_result'] = old
            result['reverse_comparison'] = compare(native[name], source(name))
            assert result['agrees'] == result['reverse_comparison']['agrees']
        rows.append(dict(body=name, members=group, **result))
        if len(rows) % 50 == 0 or name == 'wrist_fixed_bearing_fork':
            save()
            print('EXPORT RECORDS', len(rows), name, result['status'], flush=True)
    changed = [p for p, h in inputs.items() if sha(p) != h]
    unresolved = [n for r in rows if r['status'] == 'unresolved_boundary_records' for n in r['members']]
    report.update(complete=not changed, changed_during_audit=changed,
                  unresolved_names=unresolved,
                  occurrence_count=sum(len(r['members']) for r in rows),
                  evidence_counts={s:sum(len(r['members']) for r in rows if r['status'] == s)
                      for s in sorted({r['status'] for r in rows})})
    assert len(rows) == 1230 and report['occurrence_count'] == 3259
    save()
    assert not changed
    print('EXPORT RECORDS COMPLETE', report['evidence_counts'], flush=True)


if __name__ == '__main__':
    main()
