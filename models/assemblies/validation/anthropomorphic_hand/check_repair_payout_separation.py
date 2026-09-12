"""Native separation of the seven final repairs from rotating actuators.

This complements the global physical-payout rigid audit, whose input still
contains the previous thumb arm, bank and bridges. Conservative native boxes
prove these distant body pairs disjoint at all 225 authored static poses.
"""
import gzip
import json
from pathlib import Path

from native_hand_registry import HERE, native_current_bodies, sha
from check_native_reported_contacts import native_shapes
from check_full_route_bodies import placed_bounds
from lib.assembly import Body, posed_bodies
from lib.actuator_kinematics import apply_actuator_motion
from lib.layout import TENDONS


def main():
    bodies, inputs = native_current_bodies(include_reliefs=True)
    by_name = {b.name:b for b in bodies}
    folder = HERE.parents[1] / 'STEP/anthropomorphic_hand'
    repairs = []
    for filename in ('thumb_reaction_arm_clearance_r6.step', 'radial_bank_screw_clearance_candidate.step', 'fingertip_bridge_repair_review.step'):
        path = folder / filename
        inputs[str(path)] = sha(path)
        for name, shape in native_shapes(path).items():
            old = by_name[name]
            body = Body(shape,old.frame,old.system,old.kind)
            body.source_path, body.source_sha256 = str(path), sha(path)
            repairs.append(body)
    assert len(repairs) == 7
    manifest_path = HERE / 'payout_static_route_packet_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    assert manifest['complete'] and len(manifest['rows']) == 225
    assert all(sha(p) == h for p,h in manifest['input_sha256'].items())
    inputs.update(manifest['input_sha256'])
    lib = HERE.parents[1] / 'src/anthropomorphic_hand/lib'
    inputs.update({str(p):sha(p) for p in (Path(__file__),manifest_path,HERE/'check_full_route_bodies.py',
                                           lib/'assembly.py',lib/'layout.py',lib/'actuator_kinematics.py')})
    rows = []
    for sample in manifest['rows']:
        path = Path(sample['file'])
        assert sha(path) == sample['file_sha256']
        packet = json.loads(gzip.decompress(path.read_bytes()))
        assert packet['source_sha256'] == sample['source_sha256'] and packet['pose'] == sample['pose']
        moved, _, active = apply_actuator_motion(bodies,TENDONS,packet['actuator_angles_rad'])
        selected = [b for b in moved if b.name in active]
        placed = posed_bodies(repairs,sample['pose'])
        boxes = placed_bounds([*selected,*placed])
        unresolved = []
        for a in selected:
            for b in placed:
                ba,bb = boxes[a.name],boxes[b.name]
                clear = any(getattr(ba.max,k) < getattr(bb.min,k)-1e-8 or getattr(bb.max,k) < getattr(ba.min,k)-1e-8 for k in ('X','Y','Z'))
                if not clear:
                    unresolved.append([a.name,b.name])
        rows.append(dict(sample=sample['label'],pose=sample['pose'],pair_count=len(selected)*7,
                         unresolved_native_pairs=unresolved,pass_=not unresolved))
        print('REPAIR PAYOUT',sample['label'],len(selected)*7,len(unresolved),flush=True)
    changed = [p for p,h in inputs.items() if sha(p) != h]
    report = dict(scope=__doc__,input_sha256=inputs,rows=rows,sample_count=225,
                  body_revisions={b.name:dict(step_sha256=b.source_sha256,frame=b.frame) for b in repairs},
                  changed_during_audit=changed,complete=not changed,pass_=not changed and all(r['pass_'] for r in rows))
    report['pass'] = report.pop('pass_')
    (HERE/'repair_payout_separation_gate.json').write_text(json.dumps(report,indent=2)+'\n')
    assert report['pass']


if __name__ == '__main__':
    main()
