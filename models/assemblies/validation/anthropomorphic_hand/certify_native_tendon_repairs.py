"""Compose the complete physical-payout tendon gate with seven native repairs.

Unchanged pairs inherit the completed 225-pose audit. The new thumb arm has an
independent all-48-route audit over the identical payout packets. Bank material
is a native subset; five fingertip bridges have two empty directed differences.
Rigid-pair, final-export and aesthetic acceptance remain separate.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
STEP = HERE.parents[1] / 'STEP/anthropomorphic_hand'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    inputs = {str(Path(__file__)): sha(__file__)}

    def read(name, require_pass=True):
        path = HERE / name
        report = json.loads(path.read_text())
        assert report['complete'] and not report.get('changed_during_audit', [])
        if require_pass:
            assert report['pass'], name
        for filename, digest in report['input_sha256'].items():
            assert sha(filename) == digest, filename
            if filename in inputs:
                assert inputs[filename] == digest
            inputs[filename] = digest
        inputs[str(path)] = sha(path)
        return report

    baseline = read('all_native_tendon_solids_gate.json', False)
    arm = read('thumb_arm_r5_all_tendons_gate.json')
    bank = read('radial_bank_screw_clearance_gate.json')
    bridges = read('fingertip_bridge_equivalence.json')
    manifest_path = HERE / 'payout_static_route_packet_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    assert manifest['complete'] and len(manifest['rows']) == 225
    manifest_hash = sha(manifest_path)
    assert baseline['input_sha256'][str(manifest_path)] == manifest_hash
    assert arm['input_sha256'][str(manifest_path)] == manifest_hash
    for sample in manifest['rows']:
        assert sha(sample['file']) == sample['file_sha256']
    revisions = {name: dict(row) for name, row in baseline['body_revisions'].items()}
    assert len(revisions) == 3039 and baseline['tendon_count'] == arm['tendon_count'] == 48
    arm_name = 'thumb_cmc_negative_yaw_outlet_structural_jaw_1'
    assert arm['body'] == arm_name and revisions[arm_name]['frame'] == 'thumb_cmc_abduction'
    arm_step = STEP / 'thumb_reaction_arm_clearance_r5.step'
    assert arm['input_sha256'][str(arm_step)] == sha(arm_step)
    revisions[arm_name]['step_sha256'] = sha(arm_step)
    bank_name = 'thumb_radial_shared_guide_bank_structural'
    assert bank['body'] == bank_name and bank['new_minus_old_faces'] == 0
    assert bank['frame'] == revisions[bank_name]['frame'] == 'wrist_flexion'
    old_bank, new_bank = STEP / 'static_clearance_relief_review.step', STEP / 'radial_bank_screw_clearance_candidate.step'
    assert revisions[bank_name]['step_sha256'] == bank['input_sha256'][str(old_bank)]
    revisions[bank_name]['step_sha256'] = bank['input_sha256'][str(new_bank)]
    old_bridge, new_bridge = STEP / 'fingertip_pad_export_repair.step', STEP / 'fingertip_bridge_repair_review.step'
    assert len(bridges['rows']) == 5
    for row in bridges['rows']:
        assert row['pass_'] and row['old_minus_new_faces'] == row['new_minus_old_faces'] == 0
        assert revisions[row['body']]['step_sha256'] == bridges['input_sha256'][str(old_bridge)]
        revisions[row['body']]['step_sha256'] = bridges['input_sha256'][str(new_bridge)]
    base_rows = {row['sample']: row for row in baseline['rows']}
    arm_rows = {row['sample']: row for row in arm['rows']}
    assert len(base_rows) == len(arm_rows) == 225
    rows = []
    for sample in manifest['rows']:
        base_row, arm_row = base_rows[sample['label']], arm_rows[sample['label']]
        assert base_row['pose'] == arm_row['pose'] == sample['pose']
        assert len(base_row['tendon_table']) == len(arm_row['tendon_table']) == 48
        names = {r['tendon'] for r in base_row['tendon_table']}
        assert len(names) == 48 and names == {r['tendon'] for r in arm_row['tendon_table']}
        assert all(c['body'] == arm_name for c in base_row['collisions'])
        assert not arm_row['collisions'] and all(r['clear'] and not r['collisions'] for r in arm_row['tendon_table'])
        table = []
        for tendon in base_row['tendon_table']:
            assert all(c['body'] == arm_name for c in tendon['collisions'])
            table.append(dict(tendon=tendon['tendon'], clear=True, collisions=[],
                              prior_contact_count=len(tendon['collisions'])))
        rows.append(dict(sample=sample['label'], pose=sample['pose'], tendon_table=table,
                         replaced_contacts=base_row['collisions'], collisions=[], pass_=True))
    changed = [path for path, digest in inputs.items() if sha(path) != digest]
    report = dict(scope=__doc__, input_sha256=inputs, body_revisions=revisions,
                  sample_count=225, tendon_count=48, body_count=3039, rows=rows,
                  proof_transfers=dict(thumb_arm='Independent 48-route / 225-pose native audit',
                                       radial_bank='Native material subset, no new faces',
                                       fingertip_bridges='Both native directed differences empty'),
                  changed_during_audit=changed, complete=not changed, pass_=not changed)
    report['pass'] = report.pop('pass_')
    (HERE / 'all_native_repaired_tendon_solids_gate.json').write_text(json.dumps(report, indent=2) + '\n')
    print('REPAIRED NATIVE TENDONS', report['pass'], '225 poses, 48 routes, 3039 bodies')
    assert report['pass']


if __name__ == '__main__':
    main()
