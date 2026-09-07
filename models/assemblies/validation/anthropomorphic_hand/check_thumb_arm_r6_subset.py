"""R6 native subset proof and complete cap-pair / attachment follow-up.

R5's all-neighbour 225-pose gate reports exactly one pair. R6 removes material;
all other pairs inherit separation. The one cap pair is tested at every exact
authored relative pose, and the carrier attachment is independently measured.
"""
import json
from pathlib import Path

from check_native_reported_contacts import HERE, native_shapes, sha
from rigid_pose_cache import relative_pose_key
from lib.assembly import Body, posed_bodies
from lib.phalanx_r5_boolean import common, cut

NAME = 'thumb_cmc_negative_yaw_outlet_structural_jaw_1'
CAP = 'thumb_cmc_yaw_drive_-1_host_cap'
ANCHOR = 'thumb_cmc_carrier'


def main():
    gatepath = HERE / 'native_reroute_supports_r5_gate.json'
    gate = json.loads(gatepath.read_text())
    assert gate['complete'] and gate['sample_count'] == 225 and not gate['changed_during_audit']
    assert all(sha(p) == h for p, h in gate['input_sha256'].items())
    contacts = [c for r in gate['rows'] for c in r['collisions']]
    assert len(contacts) == 1 and all({c['a'],c['b']} == {NAME,CAP} for c in contacts)
    folder = HERE.parents[1] / 'STEP/anthropomorphic_hand'
    oldpath, newpath = folder / 'thumb_reaction_arm_clearance_r5.step', folder / 'thumb_reaction_arm_clearance_r6.step'
    assert gate['body_revisions'][NAME]['step_sha256'] == sha(oldpath)
    inputs = dict(gate['input_sha256'])
    inputs.update({str(p): sha(p) for p in (Path(__file__), gatepath, newpath)})
    old, new = native_shapes(oldpath)[NAME], native_shapes(newpath)[NAME]
    assert len(new.solids()) == 1 and new.is_valid
    addition = cut(new, old)
    assert not addition.faces(), ('Native subset failed', len(addition.faces()))
    parts = {NAME: new}
    for name in (CAP, ANCHOR):
        digest = gate['body_revisions'][name]['step_sha256']
        path = next(Path(p) for p,h in gate['input_sha256'].items() if p.endswith('.step') and h == digest)
        native = native_shapes(path)
        if name not in native:
            assert len(native) == 1
            native = {name: next(iter(native.values()))}
        parts[name] = native[name]
    assert gate['body_revisions'][NAME]['frame'] == gate['body_revisions'][ANCHOR]['frame'] == 'thumb_cmc_abduction'
    attachment_gap = new.solids()[0].distance_to(parts[ANCHOR].solids()[0])
    assert attachment_gap <= .025
    bodies = [Body(parts[n], gate['body_revisions'][n]['frame'], 'thumb', 'guide_mount') for n in (NAME,CAP)]
    for body, name in zip(bodies, (NAME,CAP)):
        body.shape.label = name
    cache, rows = {}, []
    for row in gate['rows']:
        key = relative_pose_key(NAME, bodies[0].frame, CAP, bodies[1].frame, row['pose'])
        if key not in cache:
            a,b = posed_bodies(bodies, row['pose'])
            hit = common(a.shape,b.shape)
            volume = sum(s.volume for s in hit.solids())
            cache[key] = volume
            print('R6 CAP', row['sample'], volume, flush=True)
        rows.append(dict(sample=row['sample'], pose=row['pose'], cap_intersection_mm3=cache[key], pass_=cache[key] <= 1e-7))
    lib = HERE.parents[1] / 'src/anthropomorphic_hand/lib'
    inputs.update({str(p):sha(p) for p in (HERE/'check_native_reported_contacts.py', HERE/'rigid_pose_cache.py',
                                           lib/'assembly.py', lib/'layout.py', lib/'phalanx_r5_boolean.py')})
    changed = [p for p,h in inputs.items() if sha(p) != h]
    report = dict(scope=__doc__, input_sha256=inputs, body=NAME, frame=bodies[0].frame,
                  old_step_sha256=sha(oldpath), new_step_sha256=sha(newpath), new_minus_old_faces=len(addition.faces()),
                  carrier_attachment_gap_mm=attachment_gap, rows=rows, sample_count=225,
                  exact_relative_cap_checks=len(cache), changed_during_audit=changed,
                  complete=not changed, pass_=not changed and all(r['pass_'] for r in rows))
    report['pass'] = report.pop('pass_')
    (HERE/'thumb_arm_r6_subset_gate.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['pass']


if __name__ == '__main__':
    main()
