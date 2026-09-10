"""Publish the completed R13 routing checks with their precise remaining limits."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    filenames = {
        'curves': 'payout_static_curves_gate.json',
        'payout': 'final_static_actuator_payout.json',
        'rigid': 'native_r13_hand_rigid_gate.json',
        'tendons': 'native_r13_tendon_gate.json',
        'moments': 'native_r13_neutral_moment_arm_gate.json',
        'payout_rigid': 'native_r13_payout_rigid_gate.json',
        'strict': 'native_r13_strict_gate.json',
        'export': 'native_r13_export_fidelity_gate.json',
        'mechanics': 'native_r13_static_mechanical_gate.json',
    }
    inputs = {str(Path(__file__)): sha(__file__)}
    docs = {}
    for key, name in filenames.items():
        path = HERE/name
        doc = docs[key] = json.loads(path.read_text())
        assert doc['complete'] and doc.get('pass', doc.get('pass_', doc.get('ok', doc.get('static_mechanics_pass', False)))), name
        inputs[str(path)] = sha(path)
        for p,h in doc['input_sha256'].items():
            assert sha(p) == h, p
            if p in inputs:
                assert inputs[p] == h, p
            inputs[p] = h
    sources = {key: {r['sample']:r for r in docs[key]['rows']}
               for key in ('curves','payout','rigid','tendons','payout_rigid')}
    samples = set(sources['curves'])
    assert len(samples) == 225 and all(set(rows)==samples for rows in sources.values())
    assert docs['rigid']['document_sha256'] == docs['tendons']['document_sha256']
    assert docs['payout_rigid']['document_sha256'] == docs['export']['document_sha256'] == docs['mechanics']['document_sha256'] == docs['rigid']['document_sha256']
    assert docs['strict']['occurrenceCount']==3259 and docs['strict']['failureCount']==0
    assert docs['strict']['selfIntersectionCheck']=='every-placement'
    neutral = sources['curves']['flat_open']['curve_gate']['tendon_table']
    names = {r['tendon'] for r in neutral}
    assert len(names) == 48
    summaries = []
    for tendon in neutral:
        name = tendon['tendon']
        curves = [next(r for r in row['curve_gate']['tendon_table'] if r['tendon']==name)
                  for row in sources['curves'].values()]
        payout = [next(r for r in row['tendons'] if r['tendon']==name)
                  for row in sources['payout'].values()]
        summaries.append(dict(tendon=name, neutral_length_mm=tendon['length_mm'],
                              minimum_radius_mm=min(r['minimum_radius_mm'] for r in curves),
                              maximum_join_gap_mm=max(r['maximum_join_gap_mm'] for r in curves),
                              maximum_tangent_error=max(r['maximum_tangent_error'] for r in curves),
                              maximum_absolute_payout_rad=max(abs(r['capstan_rotation_rad']) for r in payout),
                              maximum_length_residual_mm=max(abs(r['total_length_residual_mm']) for r in payout)))
    static = []
    for name in sorted(samples):
        rows = {k:v[name] for k,v in sources.items()}
        pose = rows['curves']['pose']
        assert all(r['pose']==pose and r.get('pass',r.get('pass_',True)) for r in rows.values()), name
        assert {r['tendon'] for r in rows['curves']['curve_gate']['tendon_table']} == names
        assert {r['tendon'] for r in rows['payout']['tendons']} == names
        assert rows['rigid']['body_count'] == rows['tendons']['body_count'] == 3041
        static.append(dict(sample=name,pose=pose,curve_and_spacing=True,hand_frame_rigid=True,
                           tendon_rigid=True,actuator_payout=True,physical_actuator_rigid=True))
    matrix = docs['moments']['joints']
    assert len(matrix)==24 and all(len(r['tendons'])==48 and r['pass'] for r in matrix)
    changed = [p for p,h in inputs.items() if sha(p)!=h]
    assert not changed
    report = dict(scope=__doc__, input_sha256=inputs,
                  document_sha256=docs['rigid']['document_sha256'],
                  tendon_summary=summaries, static_samples=static, neutral_moment_matrix=matrix,
                  sample_count=225, tendon_count=48, joint_count=24, complete=True,
                  whole_model_accepted=False,
                  static_mechanics_pass=True,
                  export_exact_material_equality_certified=False,
                  pending=['independent visual review', 'whole-hand visual acceptance',
                           'choreography and 0.02 sampling', 'staged explode and 0.05 sampling',
                           'checked Viewer with both parameters'])
    (HERE/'native_r13_routing_tables.json').write_text(json.dumps(report,indent=2)+'\n')
    lines = ['# R13 routing and static evidence', '',
             '24 axes, 48 antagonistic tendons and 48 independent actuators; 225 frozen static poses.', '',
             '**Static mechanical verification passes. The model remains unfinished.** All 3259 native occurrences pass strict every-placement validation. '
             'All 225 poses pass hand-frame rigid, physically actuated rigid, tendon/rigid, curve/spacing and payout checks. '
             'Independent visual acceptance, choreography, explode and final Viewer handoff remain open.', '',
             'The [export QA certificate](native_r13_export_fidelity_gate.json) preserves completed native material-difference proofs, '
             'fresh direct checks of 47 exported rigid bodies and complete native boundary-record comparisons for 46 variable tendons. '
             'The latter agree at 1e-10 in stored field units; that is not a global spatial-error bound. '
             'The failed exact Boolean identity diagnostic remains recorded separately.', '',
             '## Tendon table', '',
             'Lengths include the stored capstan wrap at neutral. Extrema cover all 225 static packets. Dimensions are millimeters unless stated.', '',
             '| Tendon | Neutral length | Minimum radius | Maximum payout, rad | Maximum rope-length residual |',
             '|---|---:|---:|---:|---:|']
    for row in summaries:
        lines.append(f"| {row['tendon']} | {row['neutral_length_mm']:.6f} | {row['minimum_radius_mm']:.6f} | {row['maximum_absolute_payout_rad']:.9f} | {row['maximum_length_residual_mm']:.3g} |")
    lines += ['', '## Neutral moment arms', '',
              'Finite differences check all 48 hand-side routes against each axis. Wrist transport compensation is separate. '
              'The JSON retains all 1152 matrix entries; this table shows both driven routes and the largest unintended coupling.', '',
              '| Joint | Positive, mm | Negative, mm | Maximum unintended coupling, mm |',
              '|---|---:|---:|---:|']
    for row in matrix:
        entries = {e['tendon']:e for e in row['tendons']}
        positive = entries[row['joint']+'_positive']['moment_arm_mm']
        negative = entries[row['joint']+'_negative']['moment_arm_mm']
        residual = max(abs(e['moment_arm_mm']) for e in entries.values() if e['expected_mm']==0)
        lines.append(f"| {row['joint']} | {positive:.6f} | {negative:.6f} | {residual:.3g} |")
    lines += ['', '## Static samples', '',
              'Every row passes curve/spacing, hand-frame rigid, physically actuated rigid, tendon/rigid and actuator payout checks. '
              'Unsampled transitions remain outside this static certificate.', '',
              '| Sample | Pose in degrees | Completed checks |', '|---|---|---|']
    for row in static:
        pose = ', '.join(f'{k}={v:g}' for k,v in row['pose'].items()) or 'Neutral'
        lines.append(f"| {row['sample']} | {pose} | All five pass |")
    lines += ['', 'Exact inputs, every matrix entry and scalar extrema are retained in [native_r13_routing_tables.json](native_r13_routing_tables.json).']
    (HERE/'R13_ROUTING_TABLES.md').write_text('\n'.join(lines)+'\n')
    print('R13 TABLES: 48 tendons, 24 x 48 neutral moment entries, 225 static samples')


if __name__ == '__main__':
    main()
